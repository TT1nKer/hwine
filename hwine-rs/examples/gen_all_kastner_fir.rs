use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::{generate_rtl, generate_fine_pipelined_rtl};
use std::fs;

fn build_const_fir(n_taps: usize, coeffs: &[i64]) -> (String, String) {
    let mut eg = EGraph::new();
    let mut terms = Vec::new();
    for i in 0..n_taps {
        let a = eg.add(ENode::leaf(AtomOp::Var(i * 2)));
        let c = eg.add(ENode::leaf(AtomOp::Const(coeffs[i % coeffs.len()])));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, c], DataType::default()));
        terms.push(mul);
    }
    let mut chain = terms[0];
    for i in 1..n_taps { chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], DataType::default())); }
    eg.saturate(50, 30000);
    
    let rtl_pipe = generate_fine_pipelined_rtl(&eg, chain, &format!("hwine_fir_{n_taps}"), 16);
    let rtl_comb = generate_rtl(&eg, chain, &format!("hwine_comb_fir_{n_taps}"), 16);
    (rtl_pipe, rtl_comb)
}

fn main() {
    // Use a diversified set of coefficients — FIRs typically use symmetric/antisymmetric patterns
    let coeffs = [3, 7, 13, 5, 11, 9, 2, 6, 14, 4, 10, 8];
    
    let sizes = [6, 10, 13, 20, 28, 41, 61, 71, 119, 152];
    println!("Generating hwine const-folded FIR RTL for all Kastner sizes...");
    for &n in &sizes {
        let (pipe, comb) = build_const_fir(n, &coeffs);
        fs::write(format!("hwine_fir_{}_fine.sv", n), &pipe).unwrap();
        fs::write(format!("hwine_fir_{}_comb.sv", n), &comb).unwrap();
        println!("  {n:>3}tap: pipe={:>5}ln  comb={:>5}ln", pipe.lines().count(), comb.lines().count());
    }
    println!("Done — all hwine FIR RTL files generated.");
}
