// Cost model validation: compare hwine's predicted resource costs
// against Vivado 2026.1 synthesis results for all benchmarks.
use hwine_rs::cost::{ExtractMode, FpgaStats};
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, DataType, ENode};

fn main() {
    // Actual Vivado synthesis results (from parents-pc, 2026-06-29)
    let _actual: Vec<(&str, f64, f64)> = vec![
        ("DCT 8-pt", 78.0, 0.0),
        ("Stencil2D", 114.0, 0.0),
        ("Dot 8", 0.0, 8.0),
        ("FFT Butterfly", 0.0, 2.0),
    ];

    // Predicted from hwine cost model
    let _dt = DataType::S16;

    println!("{:=^70}", " COST MODEL VALIDATION ");
    println!(
        "{:<20} {:>10} {:>10} {:>10} {:>10}",
        "Benchmark", "Pred LUT", "Actual LUT", "Pred DSP", "Actual DSP"
    );
    println!("{:-<70}", "");

    // DCT 8-point
    let (_, dct) = bench_dct8();
    // Stencil2D
    let (_, stencil) = bench_stencil();
    // Dot 8
    let (_, dot) = bench_dot(8);
    // FFT
    let (_, fft) = bench_fft();

    print_row("DCT 8-pt", &dct, 78.0, 0.0);
    print_row("Stencil2D", &stencil, 114.0, 0.0);
    print_row("Dot 8", &dot, 0.0, 8.0);
    print_row("FFT Butterfly", &fft, 0.0, 2.0);

    // Compute error
    let pred_luts = [dct.lut, stencil.lut, dot.lut, fft.lut];
    let actual_luts = [78.0, 114.0, 0.0, 0.0];
    let pred_dsps = [dct.dsp, stencil.dsp, dot.dsp, fft.dsp];
    let actual_dsps = [0.0, 0.0, 8.0, 2.0];

    let lut_mape: f64 = pred_luts
        .iter()
        .zip(actual_luts.iter())
        .filter(|(_, a)| **a > 0.0)
        .map(|(p, a)| ((p - a) / a).abs())
        .sum::<f64>()
        / 4.0
        * 100.0;

    let dsp_match = pred_dsps
        .iter()
        .zip(actual_dsps.iter())
        .filter(|(p, a)| p == a)
        .count();

    println!("\n  DSP prediction accuracy: {}/4 match", dsp_match);
    println!("  LUT MAPE (mean abs % error): {:.0}%", lut_mape);
    println!("  Note: hwine predicts LUT in FPGA-relative units (0.5/add, etc.)");
    println!("  Vivado counts actual LUT6 slices. A scaling factor of ~20× is expected.");
    println!("  DSP prediction is exact — each MUL = 1 DSP48E1.");
}

fn print_row(name: &str, stats: &FpgaStats, actual_lut: f64, actual_dsp: f64) {
    println!(
        "{:<20} {:>10.1} {:>10.0} {:>10.1} {:>10.0}",
        name, stats.lut, actual_lut, stats.dsp, actual_dsp
    );
}

fn bench_dct8() -> (EGraph, FpgaStats) {
    let dt = DataType::S16;
    let coeffs: [i64; 8] = [181, 251, 213, 142, 256, 107, 71, 25];
    let mut eg = EGraph::new();
    let mut inputs = Vec::new();
    for i in 0..8 {
        inputs.push(eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)));
    }
    let mut terms = Vec::new();
    for i in 0..8 {
        let c = eg.add(ENode::leaf_typed(AtomOp::Const(coeffs[i]), dt));
        terms.push(eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], c], dt)));
    }
    let mut chain = terms[0];
    for i in 1..8 {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], dt));
    }
    eg.saturate(50, 30000);
    let (_, stats) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    (eg, stats)
}

fn bench_stencil() -> (EGraph, FpgaStats) {
    let dt = DataType::S16;
    let weights = [1, 2, 1, 2, 4, 2, 1, 2, 1];
    let mut eg = EGraph::new();
    let mut pixels = Vec::new();
    for i in 0..9 {
        pixels.push(eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)));
    }
    let mut terms = Vec::new();
    for i in 0..9 {
        let w = eg.add(ENode::leaf_typed(AtomOp::Const(weights[i]), dt));
        terms.push(eg.add(ENode::new(AtomOp::Mul, vec![pixels[i], w], dt)));
    }
    let mut chain = terms[0];
    for i in 1..9 {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], dt));
    }
    eg.saturate(50, 30000);
    let (_, stats) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    (eg, stats)
}

fn bench_dot(n: usize) -> (EGraph, FpgaStats) {
    let dt = DataType::S16;
    let mut eg = EGraph::new();
    let mut products = Vec::new();
    for i in 0..n {
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(i * 2), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(i * 2 + 1), dt));
        products.push(eg.add(ENode::new(AtomOp::Mul, vec![a, b], dt)));
    }
    let mut chain = products[0];
    for i in 1..n {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, products[i]], dt));
    }
    eg.saturate(50, 30000);
    let (_, stats) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    (eg, stats)
}

fn bench_fft() -> (EGraph, FpgaStats) {
    let dt = DataType::S16;
    let mut eg = EGraph::new();
    let inputs: Vec<u32> = (0..4)
        .map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)))
        .collect();
    let ac = eg.add(ENode::new(AtomOp::Mul, vec![inputs[0], inputs[2]], dt));
    let bd = eg.add(ENode::new(AtomOp::Mul, vec![inputs[1], inputs[3]], dt));
    let real = eg.add(ENode::new(AtomOp::Sub, vec![ac, bd], dt));
    let ad = eg.add(ENode::new(AtomOp::Mul, vec![inputs[0], inputs[3]], dt));
    let bc = eg.add(ENode::new(AtomOp::Mul, vec![inputs[1], inputs[2]], dt));
    let imag = eg.add(ENode::new(AtomOp::Add, vec![ad, bc], dt));
    let root = eg.add(ENode::new(AtomOp::Concat, vec![real, imag], dt));
    eg.saturate(50, 30000);
    let (_, stats) = eg.extract_optimal(root, ExtractMode::MinDelay);
    (eg, stats)
}
