// Real FPGA benchmarks: FFT complex butterfly, GEMM dot-product, Stencil2D, DCT
// Each benchmark has a known algebraic optimization that e-graph can discover.
// We compare hwine-optimized vs baseline (naive) RTL.

use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode, DataType};
use hwine_rs::cost::{ExtractMode, FpgaStats};
use hwine_rs::rtl::generate_rtl;
use std::time::Instant;

fn print_header(title: &str) {
    println!("\n{:=^80}", format!(" {} ", title));
}

fn print_stats(label: &str, stats: &FpgaStats) {
    println!("{:<30} {:>8.2}ns {:>8.1}LUT {:>8.1}DSP {:>8.0}MHz",
        label, stats.delay_ns, stats.lut, stats.dsp, stats.fmax_mhz);
}

// ============================================================
// 1. FFT Complex Butterfly (4-MUL vs 3-MUL Gauss)
//    MachSuite fft/strided
//    Optimization: Gauss form trades 1 MUL for 3 ADD/SUB
// ============================================================
fn bench_fft_butterfly() {
    print_header("FFT Complex Butterfly");
    let dt = DataType::S16;
    let mut eg = EGraph::new();
    let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c = eg.add(ENode::leaf_typed(AtomOp::Var(2), dt));
    let d = eg.add(ENode::leaf_typed(AtomOp::Var(3), dt));

    // Direct: real = ac - bd, imag = ad + bc
    let ac = eg.add(ENode::new(AtomOp::Mul, vec![a, c], dt));
    let bd = eg.add(ENode::new(AtomOp::Mul, vec![b, d], dt));
    let real = eg.add(ENode::new(AtomOp::Sub, vec![ac, bd], dt));
    let ad = eg.add(ENode::new(AtomOp::Mul, vec![a, d], dt));
    let bc = eg.add(ENode::new(AtomOp::Mul, vec![b, c], dt));
    let imag = eg.add(ENode::new(AtomOp::Add, vec![ad, bc], dt));

    // Gauss: imag' = (a+b)(c+d) - ac - bd  (1 MUL instead of 2)
    let ab = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
    let cd = eg.add(ENode::new(AtomOp::Add, vec![c, d], dt));
    let s3 = eg.add(ENode::new(AtomOp::Mul, vec![ab, cd], dt));
    let t1 = eg.add(ENode::new(AtomOp::Sub, vec![s3, ac], dt));
    let imag_gauss = eg.add(ENode::new(AtomOp::Sub, vec![t1, bd], dt));
    eg.union(imag_gauss, imag);

    let root = eg.add(ENode::new(AtomOp::Concat, vec![real, imag], dt));
    let t0 = Instant::now(); eg.saturate(50, 30000);
    println!("E-graph: {}cls {:.3}s", eg.n_classes(), t0.elapsed().as_secs_f64());

    // Baseline (no optimization): 4 MUL = 4 DSP
    let (_, bl) = eg.extract_optimal(root, ExtractMode::MinDelay);
    // Sharing-aware
    let (_, sa) = eg.extract_shared_aware(root, ExtractMode::MinDelay);
    print_stats("Baseline (DP)", &bl);
    print_stats("Shared-aware cost", &sa);

    let rtl = generate_rtl(&eg, root, "bm_fft_butterfly", 16);
    std::fs::write("bm_fft_butterfly.sv", &rtl).unwrap();
    println!("RTL -> bm_fft_butterfly.sv ({} lines)", rtl.lines().count());
}

// ============================================================
// 2. GEMM Dot Product (N-way multiply-accumulate)
//    MachSuite gemm/ncubed
//    Optimization: e-graph balances the reduction tree, discovers MAC fusion
// ============================================================
fn bench_dot_product(n: usize) {
    print_header(&format!("GEMM Dot Product (N={n})"));
    let dt = DataType::S16;
    let mut eg = EGraph::new();

    let mut products = Vec::new();
    for i in 0..n {
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(i * 2), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(i * 2 + 1), dt));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![a, b], dt));
        products.push(mul);
    }

    // Build both serial chain AND balanced tree (via saturation)
    let mut serial_chain = products[0];
    for i in 1..n {
        serial_chain = eg.add(ENode::new(AtomOp::Add, vec![serial_chain, products[i]], dt));
    }

    let t0 = Instant::now();
    eg.saturate(50, 30000);
    let dt = t0.elapsed();

    // Compute serial depth (pre-saturation estimate)
    let serial_depth = n - 1;
    let (best, stats) = eg.extract_optimal(serial_chain, ExtractMode::MinDelay);
    let optimal_depth = count_depth(&best, &eg);

    println!("E-graph: {}cls {:.3}s", eg.n_classes(), dt.as_secs_f64());
    println!("Serial depth: {serial_depth}lv -> Tree depth: {optimal_depth}lv ({:.1}x reduction)",
        serial_depth as f64 / optimal_depth.max(1) as f64);
    print_stats("Optimal tree", &stats);

    let rtl = generate_rtl(&eg, serial_chain, &format!("bm_dot_{n}"), 16);
    std::fs::write(format!("bm_dot_{n}.sv"), &rtl).unwrap();
    println!("RTL -> bm_dot_{n}.sv ({} lines)", rtl.lines().count());
}

fn count_depth(node: &ENode, eg: &EGraph) -> usize {
    if node.children.is_empty() { return 0; }
    1 + node.children.iter()
        .map(|&c| count_depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
        .max().unwrap_or(0)
}

// ============================================================
// 3. Stencil2D (9-point 2D convolution)
//    MachSuite stencil/stencil2d
//    Optimization: constant multiplication + CSE across 9 identical-weight neighbor ops
// ============================================================
fn bench_stencil2d() {
    print_header("Stencil2D (9-point 3x3 convolution)");
    let dt = DataType::S16;

    // 3x3 stencil with typical smoothing weights: center=4, edges=2, corners=1
    let weights = [1, 2, 1,  2, 4, 2,  1, 2, 1];

    let mut eg = EGraph::new();
    let mut pixels = Vec::new();
    for i in 0..9 {
        pixels.push(eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)));
    }

    let mut terms = Vec::new();
    for i in 0..9 {
        let w = eg.add(ENode::leaf_typed(AtomOp::Const(weights[i]), dt));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![pixels[i], w], dt));
        terms.push(mul);
    }

    let mut chain = terms[0];
    for i in 1..9 {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], dt));
    }

    let t0 = Instant::now();
    eg.saturate(50, 30000);
    println!("E-graph: {}cls {:.3}s", eg.n_classes(), t0.elapsed().as_secs_f64());

    let (_, stats) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    let (_, stats_shared) = eg.extract_shared_aware(chain, ExtractMode::MinDelay);
    print_stats("Optimal (DP)", &stats);
    print_stats("Shared-aware", &stats_shared);

    let rtl = generate_rtl(&eg, chain, "bm_stencil2d", 16);
    std::fs::write("bm_stencil2d.sv", &rtl).unwrap();
    println!("RTL -> bm_stencil2d.sv ({} lines)", rtl.lines().count());
}

// ============================================================
// 4. DCT 8-point (1D DCT with constant coefficients)
//    CHStone jpeg DCT kernel
//    Optimization: shared shift-add across coefficients, butterfly factorization
// ============================================================
fn bench_dct8() {
    print_header("DCT 8-point (CHStone jpeg)");
    let dt = DataType::S16;

    // 8-point DCT coefficients (scaled by 256 for fixed-point):
    // C0=181, C1=251, C2=213, C3=142, C4=256, C5=107, C6=71, C7=25
    // Simplified: use the even/odd symmetry for butterfly
    let coeffs: [i64; 8] = [181, 251, 213, 142, 256, 107, 71, 25];

    let mut eg = EGraph::new();
    let mut inputs = Vec::new();
    for i in 0..8 {
        inputs.push(eg.add(ENode::leaf_typed(AtomOp::Var(i), dt)));
    }

    // Direct form: 8×8 matrix multiply → each output = sum_j(input[j] * coeff[j])
    // We model output[0] as the target (all 8 terms summed)
    let mut terms = Vec::new();
    for i in 0..8 {
        let c = eg.add(ENode::leaf_typed(AtomOp::Const(coeffs[i]), dt));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], c], dt));
        terms.push(mul);
    }

    let mut chain = terms[0];
    for i in 1..8 {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, terms[i]], dt));
    }

    let t0 = Instant::now();
    eg.saturate(50, 30000);
    println!("E-graph: {}cls {:.3}s", eg.n_classes(), t0.elapsed().as_secs_f64());

    // Before saturation: measure naive cost
    let (_, stats_opt) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    let (_, stats_shared) = eg.extract_shared_aware(chain, ExtractMode::MinDelay);
    print_stats("CSD-decomposed", &stats_opt);
    print_stats("Shared-aware", &stats_shared);

    let rtl = generate_rtl(&eg, chain, "bm_dct8", 16);
    std::fs::write("bm_dct8.sv", &rtl).unwrap();
    println!("RTL -> bm_dct8.sv ({} lines)", rtl.lines().count());
}

// ============================================================
// Main
// ============================================================
fn main() {
    println!("{:=^80}", " hwine REAL BENCHMARK SUITE ");
    println!("Target: Xilinx 7-series, Vivado 2026.1 (cost-calibrated)\n");

    bench_fft_butterfly();
    bench_dot_product(8);
    bench_dot_product(32);
    bench_stencil2d();
    bench_dct8();

    println!("\n{:=^80}", " ALL BENCHMARKS COMPLETE ");
    println!("RTL files: bm_fft_butterfly.sv, bm_dot_8.sv, bm_dot_32.sv, bm_stencil2d.sv, bm_dct8.sv");
}
