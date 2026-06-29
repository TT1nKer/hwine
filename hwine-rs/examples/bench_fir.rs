// Standard FIR filter benchmark — comparable to ROVER's FIR benchmark
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;
use std::fs;

fn main() {
    // 8-tap FIR: y[n] = sum(h[i] * x[n-i])
    // This is structurally equivalent to 8 MACs → same as ROVER's FIR benchmark
    let n = 8;
    
    // Build FIR: 8 MUL + 7 ADD (serial chain)
    let mut eg = EGraph::new();
    let mut hs = Vec::with_capacity(n);
    let mut xs = Vec::with_capacity(n);
    for i in 0..n {
        hs.push(eg.add(ENode::leaf(AtomOp::Var(i*2))));
        xs.push(eg.add(ENode::leaf(AtomOp::Var(i*2+1))));
    }
    let mut muls = Vec::with_capacity(n);
    for i in 0..n {
        muls.push(eg.add(ENode::new(AtomOp::Mul, vec![hs[i], xs[i]])));
    }
    let mut chain = muls[0];
    for i in 1..n {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, muls[i]]));
    }

    let ser_depth = n + (n-1); // MUL chain + ADD chain

    let t0 = Instant::now();
    let iters = eg.saturate_with_config(50, 20000, 15, 10, false);
    let dt = t0.elapsed();

    let (best, _) = eg.extract_optimal(chain);
    fn depth(n: &ENode, eg: &EGraph) -> usize {
        if n.children.is_empty() { 0 }
        else { 1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c).0, eg)).max().unwrap_or(0) }
    }
    let td = depth(&best, &eg);
    
    println!("FIR-8 benchmark:");
    println!("  Serial depth: {}lv ({}×MUL + {}×ADD)", ser_depth, n, n-1);
    println!("  Tree depth:   {}lv", td);
    println!("  Speedup:      {:.1}×", ser_depth as f64 / td.max(1) as f64);
    println!("  e-graph:      {}it {}cls {:.3}s", iters, eg.n_classes(), dt.as_secs_f64());
    
    // Generate RTL
    let rtl = hwine_rs::rtl::generate_rtl(&eg, chain, "fir8_tree", 16);
    fs::write("fir8_tree.sv", &rtl).unwrap();
    println!("  RTL:          {} lines", rtl.lines().count());
}
