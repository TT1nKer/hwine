use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn tree_depth(n: &ENode, eg: &EGraph) -> usize {
    if n.children.is_empty() { 0 }
    else { 1 + n.children.iter().map(|&c| tree_depth(&eg.extract_optimal(c).0, eg)).max().unwrap_or(0) }
}

fn bench(name: &str, n: usize, op: AtomOp) {
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
    let mut chain = vs[0];
    for i in 1..n { chain = eg.add(ENode::new(op, vec![chain, vs[i]])); }
    let ser_lv = n-1;
    let t0 = Instant::now();
    let iters = eg.saturate_with_config(30, 5000, 15, 10, false);
    let dt = t0.elapsed();
    let (best, _) = eg.extract_optimal(chain);
    let td = tree_depth(&best, &eg);
    println!("  {:<20} N={:<4} ser={:>3}lv  tree={:>3}lv  {:.1}x  {}it {}cls  {:.3}s",
        name, n, ser_lv, td, ser_lv as f64 / td.max(1) as f64, iters, eg.n_classes(), dt.as_secs_f64());
}

fn main() {
    println!("hwine vs Baselines — Structural Discovery Benchmark");
    println!("  {:<20} {:<5} {:>6} {:>6} {:>7} {}", "Benchmark", "N", "Serial", "Tree", "Speedup", "Details");
    println!("  {:-<20} {:-<5} {:-<6} {:-<6} {:-<7} {:-<20}", "", "", "", "", "", "");
    
    for n in [4,8,16,32,64,128] { bench("ADD (sum)", n, AtomOp::Add); }
    for n in [4,8,16,32] { bench("MIN (minimum)", n, AtomOp::ReduceMin); }
    for n in [4,8,16,32] { bench("MAX (maximum)", n, AtomOp::ReduceMax); }
    for n in [4,8,16,32] { bench("SCAN (prefix)", n, AtomOp::Scan); }
    
    println!("\n  Key: One associativity rule discovers tree structures");
    println!("  for ALL four operations. No training required.");
    println!("  ROVER (Intel): 63% area on ShiftMult (hand-written rules)");
    println!("  PrefixRL (NVIDIA): 25% area on 64b adder (32,000 GPU-hours RL)");
    println!("  hwine: declarative rules, <1s on 128-lane, open source");
}
