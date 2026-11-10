use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_pipelined_rtl;
use std::fs;

fn main() {
    let coeffs = [3, 5, 7, 2, 6, 4];
    let mut eg = EGraph::new();
    let mut terms = Vec::new();
    for (i, &k) in coeffs.iter().enumerate() {
        let a = eg.add(ENode::leaf(AtomOp::Var(i * 2)));
        let c = eg.add(ENode::leaf(AtomOp::Const(k)));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, c], DataType::default()));
        terms.push(mul);
    }
    let mut chain = terms[0];
    for i in 1..terms.len() {
        chain = eg.add(ENode::new(
            AtomOp::Add,
            vec![chain, terms[i]],
            DataType::default(),
        ));
    }

    eg.saturate_with_config(30, 5000, 15, 10, false);

    let rtl_pipe = generate_pipelined_rtl(&eg, chain, "hwine_const_fir6_pipe", 16);
    fs::write("hwine_const_fir6_pipe.sv", &rtl_pipe).unwrap();
    println!("Pipelined: {} lines", rtl_pipe.lines().count());
}
