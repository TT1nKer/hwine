// DSP48E1 pre-adder verification
// Builds Mul(Add(a,b), c) pattern, runs saturation with DSP pre-adder rule,
// generates RTL, and shows that hwine maps it to a single DSP slice.
use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, DataType, ENode};
use hwine_rs::rtl::generate_rtl;

fn main() {
    println!("{:=^60}", " DSP PRE-ADDER VERIFICATION ");
    let dt = DataType::S16;

    // ---- Test 1: Mul(Add(a,b), c) → DspPreAdd(a,b,c) ----
    println!("\n--- Test 1: Mul(Add(a,b), c) ---");
    let mut eg = EGraph::new();
    let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c = eg.add(ENode::leaf_typed(AtomOp::Var(2), dt));
    let ab = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
    let mul = eg.add(ENode::new(AtomOp::Mul, vec![ab, c], dt));

    println!("  Pre-sat: {} classes", eg.n_classes());
    eg.saturate(50, 30000);
    println!("  Post-sat: {} classes", eg.n_classes());

    let (node, stats) = eg.extract_optimal(mul, ExtractMode::MinDelay);
    println!("  Extracted op: {:?}", node.op);
    println!(
        "  Resources: LUT={:.1} DSP={:.1} delay={:.2}ns Fmax={:.0}MHz",
        stats.lut, stats.dsp, stats.delay_ns, stats.fmax_mhz
    );

    let is_preadd = matches!(node.op, AtomOp::DspPreAdd);
    println!(
        "  DSP pre-adder mapped: {}",
        if is_preadd {
            "✓ YES — single DSP slice with pre-adder"
        } else {
            "✗ NOT mapped — Mul(Add(...)) kept as separate ops"
        }
    );

    let rtl = generate_rtl(&eg, mul, "bm_dsp_preadd", 16);
    std::fs::write("bm_dsp_preadd.sv", &rtl).unwrap();
    println!("  RTL → bm_dsp_preadd.sv ({} lines)", rtl.lines().count());

    // ---- Test 2: Compare with DISTRIBUTIVE form ----
    // Mul(Add(a,b), c) vs Add(Mul(a,c), Mul(b,c))
    // With DSP pre-adder: 1 slice. Without: 2 slices (or 1 if distributive pulls apart)
    println!("\n--- Test 2: Pre-adder vs Distributive ---");
    let mut eg2 = EGraph::new();
    let a2 = eg2.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b2 = eg2.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c2 = eg2.add(ENode::leaf_typed(AtomOp::Var(2), dt));

    // Direct: Mul(Add(a,b), c) — single DSP pre-adder
    let ab2 = eg2.add(ENode::new(AtomOp::Add, vec![a2, b2], dt));
    let form1 = eg2.add(ENode::new(AtomOp::Mul, vec![ab2, c2], dt));

    // Distributed: Add(Mul(a,c), Mul(b,c)) — 2 DSPs
    let ac = eg2.add(ENode::new(AtomOp::Mul, vec![a2, c2], dt));
    let bc = eg2.add(ENode::new(AtomOp::Mul, vec![b2, c2], dt));
    let form2 = eg2.add(ENode::new(AtomOp::Add, vec![ac, bc], dt));
    eg2.union(form2, form1);

    eg2.saturate(50, 30000);
    println!("  Classes after union+saturation: {}", eg2.n_classes());

    let (n1, s1) = eg2.extract_optimal(form1, ExtractMode::MinDelay);
    let (n2, s2) = eg2.extract_optimal(form1, ExtractMode::MinDsp { max_delay_ns: 5.0 });

    println!(
        "  MinDelay: {:?} op, {:.1} DSP, {:.2}ns",
        n1.op, s1.dsp, s1.delay_ns
    );
    println!(
        "  MinDsp:   {:?} op, {:.1} DSP, {:.2}ns",
        n2.op, s2.dsp, s2.delay_ns
    );

    // Pareto
    let pareto = eg2.extract_pareto(form1);
    println!("  Pareto frontier: {} alternatives", pareto.len());
    for (i, (n, s)) in pareto.iter().enumerate() {
        println!(
            "    {}. {:?} | {:.1}DSP {:.2}ns",
            i + 1,
            n.op,
            s.dsp,
            s.delay_ns
        );
    }
}
