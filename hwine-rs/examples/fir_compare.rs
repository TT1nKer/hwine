use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use std::fs;

fn main() {
    let n = 6; // 6-tap FIR → 6 products

    let mut eg = EGraph::new();
    let mut ps = Vec::with_capacity(n);
    for i in 0..n {
        ps.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }

    let mut chain = ps[0];
    for i in 1..n {
        chain = eg.add(ENode::new(
            AtomOp::Add,
            vec![chain, ps[i]],
            DataType::default(),
        ));
    }

    eg.saturate_with_config(30, 5000, 15, 10, false);

    let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    fn depth(n: &ENode, eg: &EGraph) -> usize {
        if n.children.is_empty() {
            0
        } else {
            1 + n
                .children
                .iter()
                .map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
                .max()
                .unwrap_or(0)
        }
    }

    println!("FIR-6 ADD tree:");
    println!("  Serial depth: {}lv", n - 1);
    println!("  Tree depth:   {}lv", depth(&best, &eg));
    println!(
        "  Speedup:      {:.1}x",
        (n - 1) as f64 / depth(&best, &eg).max(1) as f64
    );

    let rtl = hwine_rs::rtl::generate_rtl(&eg, chain, "hwine_fir6_tree", 29);
    fs::write("../benchmarks/hwine_fir6_optimized.sv", &rtl).unwrap();
    println!(
        "  RTL:          {} lines → benchmarks/hwine_fir6_optimized.sv",
        rtl.lines().count()
    );
}
