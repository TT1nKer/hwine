use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_fine_pipelined_rtl;
use std::fs;

fn main() {
    // Build FIR 6-tap with const coeffs [3,5,7,2,6,4]
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

    let rtl = generate_fine_pipelined_rtl(&eg, chain, "hwine_fine_fir6", 16);
    fs::write("hwine_fine_fir6.sv", &rtl).unwrap();
    println!("Fine FIR6: {} lines", rtl.lines().count());

    // Also build one with same coeffs as Kastner? Let's check Kastner FIR
    // Generate generic add-tree fine pipelined for 6-tap too
    let mut eg_add = EGraph::new();
    let mut vs = Vec::new();
    for i in 0..6 {
        vs.push(eg_add.add(ENode::leaf(AtomOp::Var(i))));
    }
    let mut c = vs[0];
    for i in 1..6 {
        c = eg_add.add(ENode::new(AtomOp::Add, vec![c, vs[i]], DataType::default()));
    }
    eg_add.saturate_with_config(30, 5000, 15, 10, false);
    let rtl_add = generate_fine_pipelined_rtl(&eg_add, c, "hwine_fine_add6", 16);
    fs::write("hwine_fine_add6.sv", &rtl_add).unwrap();
    println!("Fine ADD6: {} lines", rtl_add.lines().count());
}
