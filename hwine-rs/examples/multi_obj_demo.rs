// Demo: multi-objective extraction
use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn build_mixed_tree(eg: &mut EGraph, n: usize) -> u32 {
    let mut vs = Vec::new();
    for i in 0..n {
        vs.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }
    // Build: ((v0*v1 + v2*v3) + (v4*v5 + v6*v7)) ...
    let mut chain = eg.add(ENode::new(
        AtomOp::Mul,
        vec![vs[0], vs[1]],
        DataType::default(),
    ));
    for i in (2..n).step_by(2) {
        if i + 1 < n {
            let mul = eg.add(ENode::new(
                AtomOp::Mul,
                vec![vs[i], vs[i + 1]],
                DataType::default(),
            ));
            chain = eg.add(ENode::new(
                AtomOp::Add,
                vec![chain, mul],
                DataType::default(),
            ));
        }
    }
    chain
}

fn main() {
    let n = 16;
    let mut eg = EGraph::new();
    let cid = build_mixed_tree(&mut eg, n);

    // Saturate
    let t0 = Instant::now();
    let iters = eg.saturate(50, 30000);
    let dt = t0.elapsed();
    println!(
        "E-graph: {iters} iterations, {} classes, {:.3}s\n",
        eg.n_classes(),
        dt.as_secs_f64()
    );

    println!("{:=^70}", " MULTI-OBJECTIVE EXTRACTION ");
    println!(
        "{:<20} {:>8} {:>8} {:>8} {:>10} {:>10}",
        "Mode", "Delay(ns)", "LUT", "DSP", "FF", "Fmax(MHz)"
    );
    println!("{:-<70}", "");

    let modes: Vec<(&str, ExtractMode)> = vec![
        ("MinDelay", ExtractMode::MinDelay),
        ("MinLut@3ns", ExtractMode::MinLut { max_delay_ns: 3.0 }),
        ("MinLut@5ns", ExtractMode::MinLut { max_delay_ns: 5.0 }),
        ("MinLut@10ns", ExtractMode::MinLut { max_delay_ns: 10.0 }),
        ("MinDsp@5ns", ExtractMode::MinDsp { max_delay_ns: 5.0 }),
        (
            "Weighted(lut)",
            ExtractMode::Weighted {
                w_delay: 0.0,
                w_lut: 1.0,
                w_dsp: 0.0,
                w_ff: 0.0,
            },
        ),
        (
            "Weighted(dsp)",
            ExtractMode::Weighted {
                w_delay: 0.0,
                w_lut: 0.0,
                w_dsp: 1.0,
                w_ff: 0.0,
            },
        ),
        (
            "Balanced",
            ExtractMode::Weighted {
                w_delay: 1.0,
                w_lut: 0.3,
                w_dsp: 2.0,
                w_ff: 0.1,
            },
        ),
    ];

    for (name, mode) in &modes {
        let (_, stats) = eg.extract_optimal(cid, *mode);
        println!(
            "{:<20} {:>8.2} {:>8.1} {:>8.1} {:>10.1} {:>10.0}",
            name, stats.delay_ns, stats.lut, stats.dsp, stats.ff, stats.fmax_mhz
        );
    }

    // Pareto frontier
    println!("\n{:=^70}", " PARETO FRONTIER ");
    let pareto = eg.extract_pareto(cid);
    println!("{} non-dominated alternatives found:\n", pareto.len());
    println!(
        "{:>3} {:>12} {:>8} {:>8} {:>10} {:>10}",
        "#", "Delay(ns)", "LUT", "DSP", "FF", "Fmax(MHz)"
    );
    println!("{:-<70}", "");
    for (i, (node, stats)) in pareto.iter().enumerate() {
        println!(
            "{:>3} {:>12.2} {:>8.1} {:>8.1} {:>10.1} {:>10.0}  [{:?}]",
            i + 1,
            stats.delay_ns,
            stats.lut,
            stats.dsp,
            stats.ff,
            stats.fmax_mhz,
            node.op
        );
    }
}
