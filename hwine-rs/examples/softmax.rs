use hwine_rs::egraph::EGraph;
use hwine_rs::cost::ExtractMode;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn main() {
    for n in [4, 8, 16, 32, 64, 128].iter() {
        let n = *n;
        let mut eg = EGraph::new();

        // Input vector
        let mut vs = Vec::with_capacity(n);
        for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
        let one = eg.add(ENode::leaf(AtomOp::One));

        // Build serial REDUCE_MAX chain
        let mut max_chain = vs[0];
        for i in 1..n { max_chain = eg.add(ENode::new(AtomOp::ReduceMax, vec![max_chain, vs[i]], DataType::default())); }

        // Build shifted values
        let mut shifted = Vec::with_capacity(n);
        for i in 0..n { shifted.push(eg.add(ENode::new(AtomOp::Sub, vec![vs[i], max_chain], DataType::default()))); }

        // Build EXP of each shifted
        let mut exp_vals = Vec::with_capacity(n);
        for i in 0..n { exp_vals.push(eg.add(ENode::new(AtomOp::Exp, vec![shifted[i]], DataType::default()))); }

        // Build serial REDUCE_ADD chain
        let mut sum_chain = exp_vals[0];
        for i in 1..n { sum_chain = eg.add(ENode::new(AtomOp::ReduceAdd, vec![sum_chain, exp_vals[i]], DataType::default())); }

        // Normalize
        let inv = eg.add(ENode::new(AtomOp::Div, vec![one, sum_chain], DataType::default()));
        for i in 0..n { eg.add(ENode::new(AtomOp::Mul, vec![exp_vals[i], inv], DataType::default())); }

        let t0 = Instant::now();
        let iters = eg.saturate_with_config(50, 30000, 15, 10, false);
        let dt = t0.elapsed();

        fn depth(n: &ENode, eg: &EGraph) -> usize {
            if n.children.is_empty() { return 0; }
            1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg)).max().unwrap_or(0)
        }

        let (best_m, _) = eg.extract_optimal(max_chain, ExtractMode::MinDelay);
        let (best_s, _) = eg.extract_optimal(sum_chain, ExtractMode::MinDelay);
        let md = depth(&best_m, &eg);
        let sd = depth(&best_s, &eg);
        let ser_lv = n - 1;
        let total_lv = md + sd + 3; // MAX tree + ADD tree + SUB + EXP + DIV

        let ncls = eg.n_classes();
        let nuns = eg.union_count;
        let secs = dt.as_secs_f64();
        let max_sp = ser_lv as f64 / md.max(1) as f64;
        let sum_sp = ser_lv as f64 / sd.max(1) as f64;
        println!(
            "Softmax N={n:3}: {iters:2}it {ncls:5}cls {nuns:6}un {secs:.3}s  MAX={ser_lv}lv->{md}lv({max_sp:.1}x)  SUM={ser_lv}lv->{sd}lv({sum_sp:.1}x)  total~{}lv->{total_lv}lv",
            ser_lv * 3,
        );
    }
}
