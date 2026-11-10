use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn bench_one(n: usize) -> (usize, f64, usize, usize) {
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n {
        vs.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }
    let mut chain = vs[0];
    for i in 1..n {
        chain = eg.add(ENode::new(
            AtomOp::Add,
            vec![chain, vs[i]],
            DataType::default(),
        ));
    }
    let t0 = Instant::now();
    let iters = eg.saturate_with_config(30, 5000, 15, 10, false);
    let dt = t0.elapsed();
    (n - 1, dt.as_secs_f64() * 1000.0, eg.n_classes(), iters)
}

fn main() {
    println!("n,serial_depth,time_ms,classes,iters");
    for n in [4, 8, 16, 32, 64, 128, 256, 512, 1024] {
        let (sd, tm, cl, it) = bench_one(n);
        println!("{n},{sd},{tm},{cl},{it}");
    }
}
