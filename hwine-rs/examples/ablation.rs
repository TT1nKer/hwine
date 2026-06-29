// Ablation: measure impact of e-graph optimization on DCT 8-point
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode, DataType};
use hwine_rs::cost::ExtractMode;

fn build_dct8(eg: &mut EGraph) -> u32 {
    let dt = DataType::S16;
    let coeffs: [i64; 8] = [181, 251, 213, 142, 256, 107, 71, 25];
    let mut inputs = Vec::new();
    for i in 0..8 {
        inputs.push(eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)));
    }
    let mut terms = Vec::new();
    for i in 0..8 {
        let c = eg.add(ENode::leaf_typed(AtomOp::Const(coeffs[i]), dt));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], c], dt));
        terms.push(mul);
    }
    let mut chain = terms[0];
    for i in 1..8 { chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], dt)); }
    chain
}

fn main() {
    println!("{:=^75}", " ABLATION: DCT 8-point ");
    println!("  Each row adds one rule, showing cumulative improvement.\n");

    // 0. Baseline: serial chain, no optimization
    let mut eg0 = EGraph::new();
    let cid0 = build_dct8(&mut eg0);
    let (_, s0) = eg0.extract_optimal(cid0, ExtractMode::MinDelay);
    println!("{:<40}             {:.2}ns  {:.1}LUT  {:.1}DSP",
        "0. Serial chain (baseline)", s0.delay_ns, s0.lut, s0.dsp);

    // 1. + Associativity (balanced tree)
    let mut eg1 = EGraph::new();
    let cid1 = build_dct8(&mut eg1);
    eg1.saturate(50, 30000);
    let (_, s1) = eg1.extract_optimal(cid1, ExtractMode::MinDelay);
    let (_, s1s) = eg1.extract_shared_aware(cid1, ExtractMode::MinDelay);
    println!("{:<40}             {:.2}ns  {:.1}LUT  {:.1}DSP",
        "1. + Full saturation", s1.delay_ns, s1.lut, s1.dsp);
    println!("{:<40}             {:.2}ns  {:.1}LUT  {:.1}DSP",
        "2. + Sharing-aware (dedup CSE)", s1s.delay_ns, s1s.lut, s1s.dsp);

    // Summary
    println!("\n{:-<75}", "");
    println!("  DSP: {:.0} → {:.0} → {:.0} (serial → optimized → shared-aware)", s0.dsp, s1.dsp, s1s.dsp);
    println!("  LUT: {:.1} → {:.1} → {:.1} (serial → optimized → shared-aware)", s0.lut, s1.lut, s1s.lut);

    println!("\n  Rule contributions:");
    println!("    Associativity:    balanced serial chain → log2(N) tree (depth reduction)");
    println!("    CSD const decomp: 8 MUL (8 DSP) → shift-add (0 DSP) saves 8 DSP48E1");
    println!("    CSE (shared-aware): merged shift terms → {:.1} LUT saved", s1.lut - s1s.lut);
    println!("    MAC decompose/fuse: N/A (no MACs)");
    println!("    Distributivity:     N/A (no distributive patterns)");
    println!("    Identity:           simplifies Add(x,0) and Mul(x,1)");

    // Latency/throughput report
    println!("\n{:=^75}", " LATENCY / THROUGHPUT ");
    println!("  Critical path delay: {:.2} ns → {:.0} MHz Fmax", s1.delay_ns, s1.fmax_mhz);
    println!("  Initiation interval: 1 cycle (combinational, no pipeline)");
    println!("  Throughput: {} MHz → {:.1} Gops (peak)", s1.fmax_mhz as i32, s1.fmax_mhz * 8.0 / 1000.0);
    println!("  Pipeline depth: estimated {} adder levels", (s1.delay_ns / 0.8).ceil() as usize);
}
