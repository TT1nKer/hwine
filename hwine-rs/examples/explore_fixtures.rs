//! Small, declared design-space experiment. Templates are the no-egraph
//! ablation; saturation is applied only to the egraph_* variants.
use hwine_rs::{
    cost::ExtractMode,
    egraph::EGraph,
    ir::{AtomOp, DataType, ENode, OverflowMode},
    rtl::{Pipeline, try_generate},
};
use std::{collections::HashSet, fs, path::PathBuf};

#[derive(Debug)]
struct Case {
    name: String,
    width: u32,
    coefficients: Vec<i64>,
}

fn parse_cases(text: &str) -> Result<Vec<Case>, String> {
    let mut lines = text.lines();
    if lines.next() != Some("case\twidth\tcoefficients") {
        return Err("expected TSV header: case, width, coefficients".into());
    }
    let mut seen = HashSet::new();
    let mut cases = Vec::new();
    for (i, line) in lines.enumerate() {
        let fields: Vec<_> = line.split('\t').collect();
        if fields.len() != 3 {
            return Err(format!(
                "line {}: expected three tab-separated fields",
                i + 2
            ));
        }
        let name = fields[0];
        if name.is_empty()
            || name.len() > 64
            || !name.as_bytes()[0].is_ascii_alphabetic()
            || !name.bytes().all(|c| c.is_ascii_alphanumeric() || c == b'_')
            || !seen.insert(name.to_owned())
        {
            return Err(format!("invalid or duplicate case name: {name}"));
        }
        let width: u32 = fields[1].parse().map_err(|_| "invalid width")?;
        if !(2..=16).contains(&width) {
            return Err("custom ECP5 experiment widths must be 2..16".into());
        }
        let coefficients: Vec<i64> = fields[2]
            .split(',')
            .map(str::parse)
            .collect::<Result<_, _>>()
            .map_err(|_| "invalid integer coefficient")?;
        if !(2..=8).contains(&coefficients.len())
            || coefficients.iter().all(|&c| c == 0)
            || coefficients
                .iter()
                .any(|&c| c < -(1i64 << (width - 1)) || c >= (1i64 << (width - 1)))
        {
            return Err(
                "require 2..8 signed, width-representable coefficients, at least one nonzero"
                    .into(),
            );
        }
        cases.push(Case {
            name: name.into(),
            width,
            coefficients,
        });
    }
    if cases.is_empty() {
        return Err("empty case manifest".into());
    }
    Ok(cases)
}

// A zero coefficient can eliminate an input from the extracted plan. Retain
// the declared tuple interface without altering its arithmetic or scheduling.
fn complete_inputs(verilog: &str, module: &str, case: &Case) -> String {
    let header = verilog.split_once("\n);").expect("generated ANSI header").0;
    let mut missing = String::new();
    for i in 0..case.coefficients.len() {
        let name = if i % 2 == 0 {
            format!("a{}", i / 2)
        } else {
            format!("w{}", i / 2)
        };
        if !header
            .lines()
            .any(|line| line.trim_end_matches(',').ends_with(&format!(" {name}")))
        {
            missing.push_str(&format!(
                "  input logic signed [{}:0] {name},\n",
                case.width - 1
            ));
        }
    }
    verilog.replacen(
        &format!("module {module}(\n"),
        &format!("module {module}(\n{missing}"),
        1,
    )
}

fn add(eg: &mut EGraph, op: AtomOp, children: Vec<u32>, dt: DataType) -> u32 {
    eg.add(ENode::new(op, children, dt))
}

fn sum(eg: &mut EGraph, xs: &[u32], dt: DataType, balanced: bool) -> u32 {
    if xs.len() == 1 {
        return xs[0];
    }
    let split = if balanced { xs.len() / 2 } else { xs.len() - 1 };
    let a = sum(eg, &xs[..split], dt, balanced);
    let b = sum(eg, &xs[split..], dt, balanced);
    add(eg, AtomOp::Add, vec![a, b], dt)
}

// Ordinary signed-digit decomposition, explicitly available to the template
// baseline too. No saturation or cost-guided selection is used here.
fn constant_mul(eg: &mut EGraph, x: u32, k: i64, dt: DataType, csd: bool) -> u32 {
    if k == 1 {
        return x;
    }
    if !csd {
        let c = eg.add(ENode::leaf_typed(AtomOp::Const(k), dt));
        return add(eg, AtomOp::Mul, vec![x, c], dt);
    }
    let mut n = k.unsigned_abs();
    let mut bit = 0;
    let mut terms = Vec::new();
    while n != 0 {
        if n & 1 != 0 {
            let digit = if n & 3 == 3 { -1 } else { 1 };
            let shifted = if bit == 0 {
                x
            } else {
                let c = eg.add(ENode::leaf_typed(AtomOp::Const(bit), DataType::U8));
                add(eg, AtomOp::Shl, vec![x, c], dt)
            };
            terms.push((digit * k.signum(), shifted));
            n = if digit < 0 { n + 1 } else { n - 1 };
        }
        bit += 1;
        n >>= 1;
    }
    // Start with a positive term where possible to avoid an unnecessary negate.
    terms.sort_by_key(|(sign, _)| -*sign);
    let mut acc = eg.add(ENode::leaf_typed(AtomOp::Zero, dt));
    for (i, (sign, term)) in terms.into_iter().enumerate() {
        acc = if i == 0 && sign > 0 {
            term
        } else {
            add(
                eg,
                if sign > 0 { AtomOp::Add } else { AtomOp::Sub },
                vec![acc, term],
                dt,
            )
        };
    }
    acc
}

fn build(coeff: &[i64], width: u32, style: &str) -> (EGraph, u32) {
    let dt = DataType {
        width,
        signed: true,
        overflow: OverflowMode::Wrap,
    };
    let mut eg = EGraph::new();
    let xs: Vec<_> = (0..coeff.len())
        .map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)))
        .collect();
    let symmetry = style.contains("symmetry");
    let csd = style.starts_with("csd");
    let native = style
        .strip_prefix("mixed_")
        .map(|s| s.rsplit('_').next().unwrap().parse::<usize>().unwrap());
    let mut terms = Vec::new();
    if symmetry {
        assert!(coeff.iter().eq(coeff.iter().rev()) && coeff.len().is_multiple_of(2));
        for i in 0..coeff.len() / 2 {
            let pair = add(
                &mut eg,
                AtomOp::Add,
                vec![xs[i], xs[coeff.len() - 1 - i]],
                dt,
            );
            let soft = csd || native.is_some_and(|j| i != j);
            terms.push(constant_mul(&mut eg, pair, coeff[i], dt, soft));
        }
    } else {
        for (i, (&x, &c)) in xs.iter().zip(coeff).enumerate() {
            let soft = csd || native.is_some_and(|j| i != j);
            terms.push(constant_mul(&mut eg, x, c, dt, soft));
        }
    }
    let root = sum(&mut eg, &terms, dt, style != "direct_left");
    if style.starts_with("egraph") {
        eg.saturate(8, 2500);
    }
    (eg, root)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut args = std::env::args().skip(1);
    let out = PathBuf::from(args.next().ok_or("output directory required")?);
    let custom = args.next();
    if args.next().is_some() {
        return Err("usage: explore_fixtures OUT [CASES.tsv]".into());
    }
    let builtin: [(&str, &[i64]); 6] = [
        ("dot3", &[7, 13, -5]),
        ("dot4", &[3, -5, 11, 7]),
        ("sym4", &[7, 13, 13, 7]),
        ("sym6", &[3, 5, 7, 7, 5, 3]),
        ("sum4", &[1, 1, 1, 1]),
        ("sum8", &[1, 1, 1, 1, 1, 1, 1, 1]),
    ];
    let cases = if let Some(path) = custom {
        parse_cases(&fs::read_to_string(path)?)?
    } else {
        [8, 12, 16]
            .into_iter()
            .flat_map(|width| {
                builtin.iter().map(move |(name, coefficients)| Case {
                    name: format!("{name}_s{width}"),
                    width,
                    coefficients: coefficients.to_vec(),
                })
            })
            .collect()
    };
    fs::create_dir_all(&out)?;
    let mut manifest = String::from(
        "name\tcase\twidth\tcoefficients\tstyle\tgroup\tinterval\tcore_latency\testimated_delay\n",
    );
    for case in cases {
        let width = case.width;
        let coeff = &case.coefficients;
        let symmetry = coeff.len().is_multiple_of(2)
            && coeff.iter().eq(coeff.iter().rev())
            && coeff.iter().any(|&c| c != 1);
        let mut styles: Vec<String> = [
            "direct_left",
            "direct_balanced",
            "csd_balanced",
            "egraph_delay",
            "egraph_dsp",
        ]
        .into_iter()
        .map(str::to_owned)
        .collect();
        if symmetry {
            styles.extend(["direct_symmetry", "csd_symmetry"].map(str::to_owned));
        }
        if coeff.iter().any(|&c| c != 1) {
            for i in 0..coeff.len() {
                styles.push(format!("mixed_{i}"));
            }
            if symmetry {
                for i in 0..coeff.len() / 2 {
                    styles.push(format!("mixed_symmetry_{i}"));
                }
            }
        }
        for style in styles {
            let (eg, root) = build(coeff, width, &style);
            let mode = if style == "egraph_dsp" {
                ExtractMode::MinDsp {
                    max_delay_ns: 1000.0,
                }
            } else {
                ExtractMode::MinDelay
            };
            let source = try_generate(&eg, root, "source", width as usize, mode, Pipeline::None)?;
            for interval in [0, 1, 2, 3] {
                let pipeline = if interval == 0 {
                    Pipeline::Output
                } else {
                    Pipeline::EveryN(interval)
                };
                let rtl = try_generate(&eg, root, "kernel", width as usize, mode, pipeline)?;
                // One common input register + at most 3 core cycles; pad
                // the output so every measured design has total latency 4.
                if rtl.latency > 3 {
                    continue;
                }
                let name = format!("{}_{style}_p{interval}", case.name);
                fs::write(
                    out.join(format!("{name}.sv")),
                    complete_inputs(&rtl.verilog, "kernel", &case),
                )?;
                fs::write(
                    out.join(format!("{name}_source.sv")),
                    complete_inputs(&source.verilog, "source", &case),
                )?;
                let group = if style.starts_with("egraph") {
                    "egraph"
                } else {
                    "template"
                };
                let coefficients = coeff
                    .iter()
                    .map(ToString::to_string)
                    .collect::<Vec<_>>()
                    .join(",");
                manifest.push_str(&format!(
                    "{name}\t{}\t{width}\t{coefficients}\t{style}\t{group}\t{interval}\t{}\t{}\n",
                    case.name, rtl.latency, source.estimated.delay_ns
                ));
            }
        }
    }
    fs::write(out.join("manifest.tsv"), manifest)?;
    Ok(())
}
