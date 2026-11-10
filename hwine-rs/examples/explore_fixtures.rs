//! Small, declared design-space experiment. Templates are the no-egraph
//! ablation; saturation is applied only to the egraph_* variants.
use hwine_rs::{
    cost::ExtractMode,
    egraph::EGraph,
    ir::{AtomOp, DataType, ENode, OverflowMode},
    rtl::{Pipeline, try_generate},
};
use std::{fs, path::PathBuf};

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
    let out = PathBuf::from(std::env::args().nth(1).expect("output directory required"));
    fs::create_dir_all(&out)?;
    let cases: [(&str, &[i64]); 6] = [
        ("dot3", &[7, 13, -5]),
        ("dot4", &[3, -5, 11, 7]),
        ("sym4", &[7, 13, 13, 7]),
        ("sym6", &[3, 5, 7, 7, 5, 3]),
        ("sum4", &[1, 1, 1, 1]),
        ("sum8", &[1, 1, 1, 1, 1, 1, 1, 1]),
    ];
    let mut manifest = String::from(
        "name\tcase\twidth\tcoefficients\tstyle\tgroup\tinterval\tcore_latency\testimated_delay\n",
    );
    for width in [8, 12, 16] {
        for (kind, coeff) in cases {
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
            if kind.starts_with("sym") {
                styles.extend(["direct_symmetry", "csd_symmetry"].map(str::to_owned));
            }
            if !kind.starts_with("sum") {
                for i in 0..coeff.len() {
                    styles.push(format!("mixed_{i}"));
                }
                if kind.starts_with("sym") {
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
                let source =
                    try_generate(&eg, root, "source", width as usize, mode, Pipeline::None)?;
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
                    let case = format!("{kind}_s{width}");
                    let name = format!("{case}_{style}_p{interval}");
                    fs::write(out.join(format!("{name}.sv")), rtl.verilog)?;
                    fs::write(out.join(format!("{name}_source.sv")), &source.verilog)?;
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
                    manifest.push_str(&format!("{name}\t{case}\t{width}\t{coefficients}\t{style}\t{group}\t{interval}\t{}\t{}\n", rtl.latency, source.estimated.delay_ns));
                }
            }
        }
    }
    fs::write(out.join("manifest.tsv"), manifest)?;
    Ok(())
}
