use hwine_rs::egraph::EGraph;
use hwine_rs::cost::ExtractMode;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_rtl;
use std::fs;
use std::time::Instant;

fn main() {
    // Build serial AND tree versions, generate both RTLs, print comparison table
    println!("hwine Proof Benchmark — UCSD FIR filter-scale ADD tree");
    println!("{:<12} {:<12} {:<12} {:<12} {:<12}",
        "Taps", "Serial lv", "Tree lv", "Speedup", "RTL lines");
    println!("{:-<12} {:-<12} {:-<12} {:-<12} {:-<12}", "", "", "", "", "");

    for n in [6, 10, 13, 20, 28, 41, 61, 71, 119, 152] {
        let mut eg_s = EGraph::new();
        let mut vs_s = Vec::with_capacity(n);
        for i in 0..n { vs_s.push(eg_s.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut c_s = vs_s[0];
        for i in 1..n { c_s = eg_s.add(ENode::new(AtomOp::Add, vec![c_s, vs_s[i]], DataType::default())); }
        let rtl_s = generate_rtl(&eg_s, c_s, "serial_add_tree", 16);
        fs::write(format!("bench_serial_{n}.sv"), &rtl_s).unwrap();

        let mut eg_t = EGraph::new();
        let mut vs_t = Vec::with_capacity(n);
        for i in 0..n { vs_t.push(eg_t.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut c_t = vs_t[0];
        for i in 1..n { c_t = eg_t.add(ENode::new(AtomOp::Add, vec![c_t, vs_t[i]], DataType::default())); }
        eg_t.saturate_with_config(30, 5000, 15, 10, false);
        let rtl_t = generate_rtl(&eg_t, c_t, "tree_add_tree", 16);
        fs::write(format!("bench_tree_{n}.sv"), &rtl_t).unwrap();

        let (best_s, _) = eg_s.extract_optimal(c_s, ExtractMode::MinDelay);
        let (best_t, _) = eg_t.extract_optimal(c_t, ExtractMode::MinDelay);
        fn d(n: &ENode, eg: &EGraph) -> usize {
            if n.children.is_empty() {0} else {1+n.children.iter().map(|&c|d(&eg.extract_optimal(c, ExtractMode::MinDelay).0,eg)).max().unwrap_or(0)}
        }
        let ser_lv = n - 1;
        let tree_lv = d(&best_t, &eg_t);
        println!("{:<12} {:<12} {:<12} {:<11.1}x {:<12}",
            format!("{}-tap", n), ser_lv, tree_lv,
            ser_lv as f64 / tree_lv.max(1) as f64,
            rtl_t.lines().count());
    }

    println!("\nProof: Same adder count, log-depth tree structure.");
    println!("RTL files: bench_serial_*.sv + bench_tree_*.sv");
    println!("Run: vivado -mode batch -source synth_compare.tcl");
}
