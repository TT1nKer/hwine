//! Deterministic RTL corpus. The reference arithmetic lives independently in
//! tools/validate.py; it does not walk this IR or reuse the RTL emitter.
use hwine_rs::{
    cost::ExtractMode,
    egraph::EGraph,
    ir::{AtomOp, DataType, ENode, OverflowMode},
    rtl::{Pipeline, try_generate},
};
use std::{fs, path::PathBuf};

fn build(kind: &str, width: u32, signed: bool) -> (EGraph, u32, Vec<u32>) {
    let mut eg = EGraph::new();
    let dt = DataType {
        width,
        signed,
        overflow: OverflowMode::Wrap,
    };
    let input_widths = match kind {
        "shl" | "shr" => vec![width, 8],
        "const_min" | "const_max" | "identity" => vec![width],
        "chain" => vec![width; 5],
        "fir3" | "mac" | "madd" | "dspmac" | "preadd" | "shared" => vec![width; 3],
        _ => vec![width; 2],
    };
    let inputs: Vec<_> = input_widths
        .iter()
        .enumerate()
        .map(|(i, &w)| {
            let t = if matches!(kind, "shl" | "shr") && i == 1 {
                DataType::U8
            } else {
                DataType { width: w, ..dt }
            };
            eg.add(ENode::leaf_typed(AtomOp::Var(i), t))
        })
        .collect();
    let root = match kind {
        "fir3" => {
            let mut terms = vec![];
            for (i, coefficient) in [7, 13, -5].into_iter().enumerate() {
                let c = eg.add(ENode::leaf_typed(AtomOp::Const(coefficient), dt));
                terms.push(eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], c], dt)));
            }
            let sum = eg.add(ENode::new(AtomOp::Add, vec![terms[0], terms[1]], dt));
            eg.add(ENode::new(AtomOp::Add, vec![sum, terms[2]], dt))
        }
        "chain" => inputs.iter().skip(1).fold(inputs[0], |acc, &x| {
            eg.add(ENode::new(AtomOp::Add, vec![acc, x], dt))
        }),
        "shared" => {
            let ab = eg.add(ENode::new(AtomOp::Mul, vec![inputs[0], inputs[1]], dt));
            let c = eg.add(ENode::new(AtomOp::Sub, vec![inputs[2], ab], dt));
            let sum = eg.add(ENode::new(AtomOp::Add, vec![ab, c], dt));
            eg.add(ENode::new(AtomOp::Add, vec![sum, ab], dt))
        }
        "const_min" | "const_max" => {
            let c = eg.add(ENode::leaf_typed(
                AtomOp::Const(if kind == "const_min" {
                    i64::MIN
                } else {
                    i64::MAX
                }),
                dt,
            ));
            eg.add(ENode::new(AtomOp::Mul, vec![inputs[0], c], dt))
        }
        "identity" => {
            let z = eg.add(ENode::leaf_typed(AtomOp::Zero, dt));
            let one = eg.add(ENode::leaf_typed(AtomOp::One, dt));
            let add = eg.add(ENode::new(AtomOp::Add, vec![inputs[0], z], dt));
            eg.add(ENode::new(AtomOp::Mul, vec![add, one], dt))
        }
        _ => {
            let op = match kind {
                "add" => AtomOp::Add,
                "sub" => AtomOp::Sub,
                "mul" => AtomOp::Mul,
                "mac" => AtomOp::Mac,
                "madd" => AtomOp::Madd,
                "dspmul" => AtomOp::DspMul,
                "dspmac" => AtomOp::DspMac,
                "preadd" => AtomOp::DspPreAdd,
                "reduceadd" => AtomOp::ReduceAdd,
                "min" => AtomOp::ReduceMin,
                "max" => AtomOp::ReduceMax,
                "shl" => AtomOp::Shl,
                "shr" => AtomOp::Shr,
                _ => panic!("unknown fixture"),
            };
            eg.add(ENode::new(op, inputs.clone(), dt))
        }
    };
    (eg, root, input_widths)
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let out = PathBuf::from(std::env::args().nth(1).expect("output directory required"));
    fs::create_dir_all(&out)?;
    let mut manifest = String::from(
        "name\tkind\twidth\tsigned\tinput_widths\tlatency\tvariant\testimated_lut\testimated_dsp\testimated_ff\testimated_delay\n",
    );
    let mut cases = vec![];
    for signed in [false, true] {
        for kind in [
            "add",
            "sub",
            "mul",
            "mac",
            "madd",
            "dspmul",
            "dspmac",
            "preadd",
            "reduceadd",
            "min",
            "max",
            "shl",
            "shr",
            "identity",
        ] {
            cases.push((kind, 4, signed));
        }
        for width in [1, 8, 16, 32, 64] {
            for kind in ["shr", "min", "max", "add", "sub", "mul", "mac"] {
                cases.push((kind, width, signed));
            }
        }
        for kind in ["const_min", "const_max"] {
            cases.push((kind, 64, signed));
        }
    }
    for width in [4, 8, 16] {
        cases.push(("fir3", width, true));
        cases.push(("chain", width, true));
        cases.push(("shared", width, true));
    }
    for (kind, width, signed) in cases {
        let (mut eg, root, input_widths) = build(kind, width, signed);
        let variants = if ["fir3", "chain", "shared"].contains(&kind) {
            vec![
                "baseline",
                "opt_delay",
                "opt_dsp",
                "pipe_output",
                "pipe_every",
                "pipe_group2",
                "pipe_group3",
            ]
        } else {
            vec!["baseline", "opt_dsp"]
        };
        for variant in variants {
            if variant != "baseline" {
                eg.saturate(12, 5000);
            }
            let mode = if variant == "opt_dsp" {
                ExtractMode::MinDsp {
                    max_delay_ns: 1000.0,
                }
            } else {
                ExtractMode::MinDelay
            };
            let pipeline = match variant {
                "pipe_output" => Pipeline::Output,
                "pipe_every" => Pipeline::EveryOp,
                "pipe_group2" => Pipeline::EveryN(2),
                "pipe_group3" => Pipeline::EveryN(3),
                _ => Pipeline::None,
            };
            let name = format!("{kind}_{}{width}_{variant}", if signed { "s" } else { "u" });
            let rtl = try_generate(&eg, root, &name, width as usize, mode, pipeline)?;
            fs::write(out.join(format!("{name}.sv")), &rtl.verilog)?;
            if pipeline != Pipeline::None {
                let source = try_generate(
                    &eg,
                    root,
                    &format!("{name}_source"),
                    width as usize,
                    mode,
                    Pipeline::None,
                )?;
                fs::write(out.join(format!("{name}_source.sv")), &source.verilog)?;
            }

            let widths = input_widths
                .iter()
                .map(|n| n.to_string())
                .collect::<Vec<_>>()
                .join(",");
            manifest.push_str(&format!(
                "{name}\t{kind}\t{width}\t{signed}\t{widths}\t{}\t{variant}\t{}\t{}\t{}\t{}\n",
                rtl.latency,
                rtl.estimated.lut,
                rtl.estimated.dsp,
                rtl.estimated.ff,
                rtl.estimated.delay_ns
            ));
        }
    }
    fs::write(out.join("manifest.tsv"), manifest)?;
    Ok(())
}
