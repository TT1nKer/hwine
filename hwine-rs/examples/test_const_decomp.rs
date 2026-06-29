use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_rtl;

fn test_coeff(k: i64) {
    let mut eg = EGraph::new();
    let a = eg.add(ENode::leaf(AtomOp::Var(0)));
    let c = eg.add(ENode::leaf(AtomOp::Const(k)));
    let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, c]));
    
    eg.saturate_with_config(30, 5000, 15, 10, false);
    
    let (best, cost) = eg.extract_optimal(mul);
    println!("{k}*a -> cost={cost:.1}  {best:?}");
}

fn main() {
    println!("=== Const decomposition tests ===");
    for k in [2, 3, 5, 6, 7, 10, 11, 13, 14, 15, 21, 31, 63] {
        test_coeff(k);
    }
    
    // Test FIR-like: sum of (coeff_i * a)
    println!("\n=== FIR 6-tap with const coeffs ===");
    let coeffs = [3, 5, 7, 2, 6, 4];
    let mut eg = EGraph::new();
    let mut terms = Vec::new();
    for (i, &k) in coeffs.iter().enumerate() {
        let a = eg.add(ENode::leaf(AtomOp::Var(i * 2)));
        let c = eg.add(ENode::leaf(AtomOp::Const(k)));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, c]));
        terms.push(mul);
    }
    let mut chain = terms[0];
    for i in 1..terms.len() { chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]])); }
    
    eg.saturate_with_config(30, 5000, 15, 10, false);
    
    let (best, cost) = eg.extract_optimal(chain);
    let rtl = generate_rtl(&eg, chain, "fir6_const", 16);
    println!("FIR6: cost={cost:.1}  RTL lines={}", rtl.lines().count());
    println!("Best: {best:?}");
    
    // Save RTL for inspection
    std::fs::write("fir6_const_test.sv", &rtl).unwrap();
    println!("Saved fir6_const_test.sv");
}
