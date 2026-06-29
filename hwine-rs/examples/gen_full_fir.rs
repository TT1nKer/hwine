use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::{generate_rtl, generate_pipelined_rtl};
use std::fs;

fn build_fir_eg(n_taps: usize) -> (EGraph, u32, EGraph, u32) {
    // FIR: sum(a_i * w_i)
    let mut eg = EGraph::new();
    let mut mul_results = Vec::with_capacity(n_taps);
    for i in 0..n_taps {
        let a = eg.add(ENode::leaf(AtomOp::Var(i * 2)));
        let w = eg.add(ENode::leaf(AtomOp::Var(i * 2 + 1)));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, w]));
        mul_results.push(mul);
    }
    // Serial sum chain (for serial baseline)
    let mut chain = mul_results[0];
    for i in 1..n_taps {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, mul_results[i]]));
    }
    
    // Tree sum (saturate for tree discovery)
    let mut eg_tree = EGraph::new();
    let mut mul_results_t = Vec::with_capacity(n_taps);
    for i in 0..n_taps {
        let a = eg_tree.add(ENode::leaf(AtomOp::Var(i * 2)));
        let w = eg_tree.add(ENode::leaf(AtomOp::Var(i * 2 + 1)));
        let mul = eg_tree.add(ENode::new(AtomOp::Mul, vec![a, w]));
        mul_results_t.push(mul);
    }
    let mut chain_t = mul_results_t[0];
    for i in 1..n_taps {
        chain_t = eg_tree.add(ENode::new(AtomOp::Add, vec![chain_t, mul_results_t[i]]));
    }
    eg_tree.saturate_with_config(30, 10000, 20, 15, false);
    
    (eg, chain, eg_tree, chain_t)
}

fn main() {
    for n in [6, 13, 20, 41] {
        let (eg_s, chain_s, eg_t, chain_t) = build_fir_eg(n);
        
        let rtl_serial = generate_rtl(&eg_s, chain_s, &format!("full_fir_{n}_serial"), 16);
        let rtl_tree = generate_rtl(&eg_t, chain_t, &format!("full_fir_{n}_tree"), 16);
        let rtl_pipe = generate_pipelined_rtl(&eg_t, chain_t, &format!("full_fir_{n}_pipe"), 16);
        
        fs::write(format!("full_fir_{n}_serial.sv"), &rtl_serial).unwrap();
        fs::write(format!("full_fir_{n}_tree.sv"), &rtl_tree).unwrap();
        fs::write(format!("full_fir_{n}_pipe.sv"), &rtl_pipe).unwrap();
        
        let sl = rtl_serial.lines().count();
        let tl = rtl_tree.lines().count();
        let pl = rtl_pipe.lines().count();
        println!("{n}-tap: serial={sl}ln tree={tl}ln pipe={pl}ln");
    }
    println!("Done. Files: full_fir_*_{{serial,tree,pipe}}.sv");
}
