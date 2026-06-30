// Streaming FIR filter with pipeline retiming
// Demonstrates automatic FIFO insertion via rule_pipeline_retime.
// The e-graph creates pipeline stage options (StreamFifo) at every arithmetic
// operation. Multi-objective extraction then selects FIFO placement based on
// the delay vs FF tradeoff.
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode, DataType};
use hwine_rs::cost::ExtractMode;
use hwine_rs::rtl::generate_rtl;

fn main() {
    println!("{:=^60}", " STREAMING FIR BENCHMARK ");
    let dt = DataType::S16;

    // Build a 5-tap FIR: y = x0*c0 + x1*c1 + x2*c2 + x3*c3 + x4*c4
    let taps: [i64; 5] = [13, -7, 31, 7, -17];
    let mut eg = EGraph::new();

    let inputs: Vec<u32> = (0..5).map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), dt))).collect();
    let coeffs: Vec<u32> = taps.iter().map(|&c| eg.add(ENode::leaf_typed(AtomOp::Const(c), dt))).collect();

    let mut terms = Vec::new();
    for i in 0..5 {
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], coeffs[i]], dt));
        terms.push(mul);
    }
    let mut fir = terms[0];
    for i in 1..5 {
        fir = eg.add(ENode::new(AtomOp::Add, vec![fir, terms[i]], dt));
    }

    let pre_classes = eg.n_classes();
    println!("  Pre-saturation: {} classes", pre_classes);

    // Saturate with pipeline retiming enabled
    let _iters = eg.saturate_retime(100, 30000);
    let post_classes = eg.n_classes();
    println!("  Post-saturation: {} classes ({} iterations)", post_classes, _iters);

    // ---- Extraction Modes ----
    println!("\n{:-^60}", " EXTRACTION MODES ");

    // 1. MinDelay (combination): choose the path with lowest delay
    let (n1, s1) = eg.extract_optimal(fir, ExtractMode::MinDelay);
    println!("\n  MinDelay:");
    println!("    Op: {:?} | LUT={:.1} FF={:.1} DSP={:.1} delay={:.2}ns cycles={} Fmax={:.0}MHz",
        n1.op, s1.lut, s1.ff, s1.dsp, s1.delay_ns, s1.cycles, s1.fmax_mhz);
    let rtl1 = generate_rtl(&eg, fir, "bm_stream_fir_min_delay", 16);
    std::fs::write("bm_stream_fir_min_delay.sv", &rtl1).unwrap();
    println!("    RTL: {} lines", rtl1.lines().count());

    // 2. MinFF: prefer no FIFOs (minimal flip-flops)
    let (n2, s2) = eg.extract_optimal(fir, ExtractMode::MinFf { max_delay_ns: 10.0 });
    println!("\n  MinFF (max_delay<=10ns):");
    println!("    Op: {:?} | LUT={:.1} FF={:.1} DSP={:.1} delay={:.2}ns cycles={} Fmax={:.0}MHz",
        n2.op, s2.lut, s2.ff, s2.dsp, s2.delay_ns, s2.cycles, s2.fmax_mhz);

    // 3. MinDelay with pipeline constraint: force Fmax > 300MHz
    //    This requires inserting FIFOs to break long combinational paths
    let (n3, s3) = eg.extract_optimal(fir, ExtractMode::MinFf { max_delay_ns: 3.0 });
    println!("\n  MinFF (max_delay<=3ns, pipeline):");
    println!("    Op: {:?} | LUT={:.1} FF={:.1} DSP={:.1} delay={:.2}ns cycles={} Fmax={:.0}MHz",
        n3.op, s3.lut, s3.ff, s3.dsp, s3.delay_ns, s3.cycles, s3.fmax_mhz);
    let rtl3 = generate_rtl(&eg, fir, "bm_stream_fir_pipelined", 16);
    std::fs::write("bm_stream_fir_pipelined.sv", &rtl3).unwrap();
    println!("    RTL: {} lines", rtl3.lines().count());

    // 4. Weighted: balance delay and FF
    let (n4, s4) = eg.extract_optimal(fir, ExtractMode::Weighted { w_delay: 0.6, w_lut: 0.1, w_dsp: 0.2, w_ff: 0.1 });
    println!("\n  Weighted (delay*0.6 + LUT*0.1 + DSP*0.2 + FF*0.1):");
    println!("    Op: {:?} | LUT={:.1} FF={:.1} DSP={:.1} delay={:.2}ns cycles={} Fmax={:.0}MHz",
        n4.op, s4.lut, s4.ff, s4.dsp, s4.delay_ns, s4.cycles, s4.fmax_mhz);

    // ---- Pareto Frontier ----
    let pareto = eg.extract_pareto(fir);
    println!("\n{:-^60}", " PARETO FRONTIER ");
    println!("  {} non-dominated alternatives:\n", pareto.len());
    println!("  {:>3} {:>10} {:>8} {:>8} {:>8} {:>10}   {:?}", "#", "Delay(ns)", "LUT", "FF", "DSP", "Cycles", "Op");
    println!("  {}", "-".repeat(60));
    for (i, (n, s)) in pareto.iter().enumerate() {
        println!("  {:>3} {:>10.2} {:>8.1} {:>8.1} {:>8.1} {:>10}   {:?}",
            i + 1, s.delay_ns, s.lut, s.ff, s.dsp, s.cycles, n.op);
    }

    // ---- Shared-aware cost ----
    let (n5, s5) = eg.extract_shared_aware(fir, ExtractMode::MinDelay);
    println!("\n{:-^60}", " SHARED-AWARE ");
    println!("  Op: {:?} | LUT={:.1} FF={:.1} DSP={:.1} delay={:.2}ns cycles={}",
        n5.op, s5.lut, s5.ff, s5.dsp, s5.delay_ns, s5.cycles);

    println!("\n{:=^60}", " COMPLETE ");
}
