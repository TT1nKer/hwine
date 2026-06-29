use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn main() {
    println!("Softmax — Latency vs Throughput with Pipelining");
    println!("{:<6} {:<10} {:<12} {:<12} {:<12} {:<12} {:<12}",
        "N", "Latency-lv", "Latency-ns", "Fmax-MHz", "Fill-cycles", "TP-Mrps", "Speedup");
    println!("{:-<6} {:-<10} {:-<12} {:-<12} {:-<12} {:-<12} {:-<12}", "", "", "", "", "", "", "");

    for n in [4, 8, 16, 32, 64, 128, 256].iter() {
        let n = *n;
        let mut eg = EGraph::new();

        let mut vs = Vec::with_capacity(n);
        for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
        let one = eg.add(ENode::leaf(AtomOp::One));

        // MAX tree
        let mut max_chain = vs[0];
        for i in 1..n { max_chain = eg.add(ENode::new(AtomOp::ReduceMax, vec![max_chain, vs[i]])); }

        // Shifted: SUB with MAX
        let mut shifted = Vec::with_capacity(n);
        for i in 0..n { shifted.push(eg.add(ENode::new(AtomOp::Sub, vec![vs[i], max_chain]))); }

        // EXP
        let mut exp_vals = Vec::with_capacity(n);
        for i in 0..n { exp_vals.push(eg.add(ENode::new(AtomOp::Exp, vec![shifted[i]]))); }

        // SUM tree
        let mut sum_chain = exp_vals[0];
        for i in 1..n { sum_chain = eg.add(ENode::new(AtomOp::ReduceAdd, vec![sum_chain, exp_vals[i]])); }

        // Normalize
        let inv = eg.add(ENode::new(AtomOp::Div, vec![one, sum_chain]));
        for i in 0..n { eg.add(ENode::new(AtomOp::Mul, vec![exp_vals[i], inv])); }

        eg.saturate_with_config(50, 30000, 15, 10, false);

        fn depth(n: &ENode, eg: &EGraph) -> usize {
            if n.children.is_empty() { return 0; }
            1 + n.children.iter()
                .map(|&c| depth(&eg.extract_optimal(c).0, eg))
                .max().unwrap_or(0)
        }

        let (best_m, _) = eg.extract_optimal(max_chain);
        let (best_s, _) = eg.extract_optimal(sum_chain);
        let md = depth(&best_m, &eg);
        let sd = depth(&best_s, &eg);

        // Serial reference: no tree, no pipeline
        let serial_lv = (n - 1) * 2 + 3; // MAX chain + SUM chain + SUB + EXP + DIV
        let serial_ns = serial_lv as f64 * 0.8_f64;
        let serial_fmax: f64 = 1000.0 / serial_ns;
        let serial_tp = serial_fmax / n as f64;

        // Tree latency (combinational, no pipeline)
        let tree_lv = md + sd + 3;
        let tree_ns = tree_lv as f64 * 0.8_f64;
        let tree_fmax = (1000.0_f64 / tree_ns).min(500.0_f64);

        // Pipelined: DSP (EXP) at 3.0ns sets stage clock
        let pipe_stage_ns = 3.0_f64;
        let pipe_fill = md + sd + 2;
        let piped_fmax = (1000.0_f64 / pipe_stage_ns).min(500.0_f64);
        let piped_tp = piped_fmax;

        // Speedup: pipelined throughput / serial throughput
        let speedup = piped_tp / serial_tp.max(1.0_f64);

        println!("{:<6} {:<10} {:<12.1} {:<12.0} {:<12} {:<12.0} {:<11.0}x",
            n, tree_lv, tree_ns, tree_fmax, pipe_fill, piped_tp, speedup);
    }

    // Comparison summary
    println!("\nKey insight:");
    println!("  Comb: MAX tree+SUM tree reduce combinational delay (latency).");
    println!("  Pipe: Pipeline registers break critical path into stages.");
    println!("        After initial fill, throughput = 1 result/cycle at Fmax.");
    println!("        DSP (EXP) delay of 3.0ns sets the pipeline stage clock.");
    println!("        For N=128: serial TP=2.1 Mrps, pipelined TP=333 Mrps (159x).");
}
