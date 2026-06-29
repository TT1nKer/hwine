use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::{generate_rtl, generate_pipelined_rtl};
use std::fs;

fn main() {
    let sizes = [20, 41, 61, 119];
    
    for &n in &sizes {
        // Serial
        let mut eg_s = EGraph::new();
        let mut vs_s = Vec::with_capacity(n);
        for i in 0..n { vs_s.push(eg_s.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut c_s = vs_s[0];
        for i in 1..n { c_s = eg_s.add(ENode::new(AtomOp::Add, vec![c_s, vs_s[i]])); }
        let rtl_s = generate_rtl(&eg_s, c_s, &format!("serial_fir_{n}"), 16);
        fs::write(format!("rtl_serial_fir_{n}.sv"), &rtl_s).unwrap();

        // Tree (unpiped, same as before)
        let mut eg_t = EGraph::new();
        let mut vs_t = Vec::with_capacity(n);
        for i in 0..n { vs_t.push(eg_t.add(ENode::leaf(AtomOp::Var(i)))); }
        let mut c_t = vs_t[0];
        for i in 1..n { c_t = eg_t.add(ENode::new(AtomOp::Add, vec![c_t, vs_t[i]])); }
        eg_t.saturate_with_config(30, 5000, 15, 10, false);
        let rtl_t = generate_rtl(&eg_t, c_t, &format!("tree_fir_{n}"), 16);
        fs::write(format!("rtl_tree_fir_{n}.sv"), &rtl_t).unwrap();

        // Pipelined tree
        let rtl_p = generate_pipelined_rtl(&eg_t, c_t, &format!("pipe_fir_{n}"), 16);
        fs::write(format!("rtl_pipe_fir_{n}.sv"), &rtl_p).unwrap();
    }

    println!("Generated RTL files for serial, tree, and pipelined FIRs");
    println!("Sizes: 20, 41, 61, 119 taps");
    for &n in &sizes {
        for prefix in &["serial", "tree", "pipe"] {
            let f = format!("rtl_{prefix}_fir_{n}.sv");
            println!("  {}: {} lines", f, fs::read_to_string(&f).unwrap().lines().count());
        }
    }
}
