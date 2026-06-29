// Prefix circuit benchmark — comparable to NVIDIA PrefixRL
use hwine_rs::egraph::EGraph;
use hwine_rs::cost::ExtractMode;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn main() {
    // 32-bit prefix circuit (adder carry chain equivalent)
    // Each stage: SCAN(a_i, a_{i-1}) — parallel prefix
    let n = 32;
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
    
    let mut chain = eg.add(ENode::new(AtomOp::Scan, vec![vs[0], vs[1]], DataType::default()));
    for i in 2..n { chain = eg.add(ENode::new(AtomOp::Scan, vec![chain, vs[i]], DataType::default())); }

    let ser_depth = n - 1;

    let t0 = Instant::now();
    let iters = eg.saturate_with_config(50, 20000, 15, 10, false);
    let dt = t0.elapsed();

    let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    fn depth(n: &ENode, eg: &EGraph) -> usize {
        if n.children.is_empty() { 0 }
        else { 1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg)).max().unwrap_or(0) }
    }
    let td = depth(&best, &eg);

    println!("Prefix-32 (SCAN chain):");
    println!("  Serial depth: {}lv", ser_depth);
    println!("  Tree depth:   {}lv", td);
    println!("  Speedup:      {:.1}×", ser_depth as f64 / td.max(1) as f64);
    println!("  e-graph:      {}it {}cls {:.3}s", iters, eg.n_classes(), dt.as_secs_f64());
}
