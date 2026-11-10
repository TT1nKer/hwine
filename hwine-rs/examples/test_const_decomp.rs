use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_rtl;

fn test_coeff(k: i64) {
    let mut eg = EGraph::new();
    let a = eg.add(ENode::leaf(AtomOp::Var(0)));
    let c = eg.add(ENode::leaf(AtomOp::Const(k)));
    let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, c], DataType::default()));

    eg.saturate_with_config(30, 5000, 15, 10, false);

    let (best, stats) = eg.extract_optimal(mul, ExtractMode::MinDelay);
    println!(
        "{k:>3}*a -> delay={:.2}ns LUT={:.1} DSP={:.1}  {best:?}",
        stats.delay_ns, stats.lut, stats.dsp
    );
}

fn main() {
    println!("=== Const decomposition tests (CSD) ===");
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

    let (best, stats) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    let rtl = generate_rtl(&eg, chain, "fir6_const", 16);
    println!(
        "FIR6: delay={:.2}ns LUT={:.1} DSP={:.1}  RTL lines={}",
        stats.delay_ns,
        stats.lut,
        stats.dsp,
        rtl.lines().count()
    );
    println!("Best: {best:?}");

    // Save RTL for inspection
    std::fs::write("fir6_const_test.sv", &rtl).unwrap();
    println!("Saved fir6_const_test.sv");
}
