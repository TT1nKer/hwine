use hwine_rs::egraph::EGraph;
use hwine_rs::cost::ExtractMode;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::{generate_fine_pipelined_rtl, generate_rtl};
use std::time::Instant;
use std::fs;

// ====== Experiment 1: E-graph runtime scaling ======
fn bench_scaling() {
    println!("=== Experiment 1: E-graph runtime scaling ===");
    println!("N\tTime(ms)\tClasses\tIters\tSpeedup");
    for n in [4, 8, 16, 32, 64, 128, 256, 512] {
        let mut eg = EGraph::new();
        let mut vs = Vec::with_capacity(n);
        for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut chain = vs[0];
        for i in 1..n { chain = eg.add(ENode::new(AtomOp::Add, vec![chain, vs[i]], DataType::default())); }
        let t0 = Instant::now();
        let iters = eg.saturate_with_config(30, 5000, 15, 10, false);
        let dt = t0.elapsed();
        let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
        fn depth(n: &ENode, eg: &EGraph) -> usize {
            if n.children.is_empty() { 0 } else { 1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg)).max().unwrap_or(0) }
        }
        let td = depth(&best, &eg);
        println!("{}\t{:.2}\t{}\t{}\t{:.1}x", n, dt.as_secs_f64() * 1000.0, eg.n_classes(), iters, (n - 1) as f64 / td.max(1) as f64);
    }
    println!();
}

// ====== Experiment 2: Naive balanced tree (no e-graph) ======
fn build_balanced_adds(n: usize, start_id: &mut usize) -> ENode {
    if n == 1 {
        *start_id += 1;
        return ENode::leaf(AtomOp::Var(*start_id - 1));
    }
    let left = build_balanced_adds(n / 2, start_id);
    let right = build_balanced_adds(n - n / 2, start_id);
    ENode::new(AtomOp::Add, vec![0, 1], DataType::default()) // placeholder children, will rebuild
}

fn bench_ablation() {
    println!("=== Experiment 2: Ablation — naive tree vs e-graph ===");
    println!("Taps\tNaiveFmax\tEgraphFmax\tLUT_naive\tLUT_egraph");
    
    for &n in &[6, 10, 20, 41] {
        // Naive balanced tree (recursive binary split)
        let mut eg_naive = EGraph::new();
        let mut vs = Vec::new();
        for i in 0..n { vs.push(eg_naive.add(ENode::leaf(AtomOp::Var(i)))); }
        // Build balanced tree manually
        let root = build_balanced_tree(&mut eg_naive, &vs);
        let rtl_naive = generate_fine_pipelined_rtl(&eg_naive, root, &format!("naive_bal_{n}"), 16);
        fs::write(format!("paper_naive_bal_{n}.sv"), &rtl_naive).unwrap();
        
        // e-graph optimized tree
        let mut eg_opt = EGraph::new();
        let mut vs2 = Vec::new();
        for i in 0..n { vs2.push(eg_opt.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut chain = vs2[0];
        for i in 1..n { chain = eg_opt.add(ENode::new(AtomOp::Add, vec![chain, vs2[i]], DataType::default())); }
        eg_opt.saturate_with_config(30, 5000, 15, 10, false);
        let rtl_opt = generate_fine_pipelined_rtl(&eg_opt, chain, &format!("egraph_opt_{n}"), 16);
        fs::write(format!("paper_egraph_opt_{n}.sv"), &rtl_opt).unwrap();
        
        println!("{n}\tnaive_{n}\teg_{n}\t{}\t{}",
            rtl_naive.lines().count(), rtl_opt.lines().count());
    }
    println!("RTL files: paper_naive_bal_*.sv + paper_egraph_opt_*.sv");
    println!();
}

fn build_balanced_tree(eg: &mut EGraph, leaves: &[u32]) -> u32 {
    if leaves.len() == 1 { return leaves[0]; }
    let mid = leaves.len() / 2;
    let left = build_balanced_tree(eg, &leaves[..mid]);
    let right = build_balanced_tree(eg, &leaves[mid..]);
    eg.add(ENode::new(AtomOp::Add, vec![left, right], DataType::default()))
}

fn main() {
    bench_scaling();
    bench_ablation();
}
