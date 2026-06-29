use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn bench_one(n: usize) -> (usize, f64, usize, usize) {
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
    let mut chain = vs[0];
    for i in 1..n { chain = eg.add(ENode::new(AtomOp::Add, vec![chain, vs[i]])); }
    let t0 = Instant::now();
    let iters = eg.saturate_with_config(30, 5000, 15, 10, false);
    let dt = t0.elapsed();
    let (best, _) = eg.extract_optimal(chain);
    fn depth(n: &ENode, eg: &EGraph) -> usize {
        if n.children.is_empty() { 0 } else { 1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c).0, eg)).max().unwrap_or(0) }
    }
    (n - 1, dt.as_secs_f64() * 1000.0, eg.n_classes(), iters)
}

fn main() {
    println!("n,serial_depth,time_ms,classes,iters");
    for n in [4, 8, 16, 32, 64, 128, 256, 512, 1024] {
        let (sd, tm, cl, it) = bench_one(n);
        println!("{n},{sd},{tm},{cl},{it}");
    }
}
