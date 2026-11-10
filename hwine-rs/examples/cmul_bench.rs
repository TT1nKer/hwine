// Complex multiply benchmark: direct (4-MUL) vs Gauss (3-MUL) form
// Before e-graph union, show raw resource comparison.
// After union, show that the e-graph preserves both forms.

use hwine_rs::cost::{ExtractMode, FpgaStats};
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, DataType, ENode};
use std::time::Instant;

fn build_direct(eg: &mut EGraph, a: u32, b: u32, c: u32, d: u32, dt: DataType) -> u32 {
    let ac = eg.add(ENode::new(AtomOp::Mul, vec![a, c], dt));
    let bd = eg.add(ENode::new(AtomOp::Mul, vec![b, d], dt));
    let real = eg.add(ENode::new(AtomOp::Sub, vec![ac, bd], dt));
    let ad = eg.add(ENode::new(AtomOp::Mul, vec![a, d], dt));
    let bc = eg.add(ENode::new(AtomOp::Mul, vec![b, c], dt));
    let imag = eg.add(ENode::new(AtomOp::Add, vec![ad, bc], dt));
    eg.add(ENode::new(AtomOp::Concat, vec![real, imag], dt))
}

fn build_gauss(eg: &mut EGraph, a: u32, b: u32, c: u32, d: u32, dt: DataType) -> u32 {
    let ac = eg.add(ENode::new(AtomOp::Mul, vec![a, c], dt));
    let bd = eg.add(ENode::new(AtomOp::Mul, vec![b, d], dt));
    let real = eg.add(ENode::new(AtomOp::Sub, vec![ac, bd], dt));
    let ab = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
    let cd = eg.add(ENode::new(AtomOp::Add, vec![c, d], dt));
    let s3 = eg.add(ENode::new(AtomOp::Mul, vec![ab, cd], dt));
    let t1 = eg.add(ENode::new(AtomOp::Sub, vec![s3, ac], dt));
    let imag = eg.add(ENode::new(AtomOp::Sub, vec![t1, bd], dt));
    eg.add(ENode::new(AtomOp::Concat, vec![real, imag], dt))
}

fn print_stats(label: &str, stats: &FpgaStats) {
    println!(
        "{:<20} {:>8.2} {:>8.1} {:>8.1} {:>10.1} {:>10.0}",
        label, stats.delay_ns, stats.lut, stats.dsp, stats.ff, stats.fmax_mhz
    );
}

fn main() {
    let dt = DataType::S16;

    // ---- Before union: compare raw forms ----
    println!("===== RAW FORMS (before e-graph union) =====\n");
    println!(
        "{:<20} {:>8} {:>8} {:>8} {:>10} {:>10}",
        "Form", "Delay(ns)", "LUT", "DSP", "FF", "Fmax(MHz)"
    );
    println!("{:-<70}", "");

    let mut eg1 = EGraph::new();
    let a1 = eg1.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b1 = eg1.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c1 = eg1.add(ENode::leaf_typed(AtomOp::Var(2), dt));
    let d1 = eg1.add(ENode::leaf_typed(AtomOp::Var(3), dt));
    let root_d = build_direct(&mut eg1, a1, b1, c1, d1, dt);
    let (_, sd) = eg1.extract_optimal(root_d, ExtractMode::MinDelay);
    print_stats("Direct (4-MUL)", &sd);

    let mut eg2 = EGraph::new();
    let a2 = eg2.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b2 = eg2.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c2 = eg2.add(ENode::leaf_typed(AtomOp::Var(2), dt));
    let d2 = eg2.add(ENode::leaf_typed(AtomOp::Var(3), dt));
    let root_g = build_gauss(&mut eg2, a2, b2, c2, d2, dt);
    let (_, sg) = eg2.extract_optimal(root_g, ExtractMode::MinDelay);
    print_stats("Gauss (3-MUL)", &sg);

    println!(
        "\n  MUL tradeoff: {} → {} (Gauss saves {} MUL)",
        sd.dsp,
        sg.dsp,
        sd.dsp - sg.dsp
    );
    println!(
        "  LUT tradeoff: {} → {} (Gauss adds {} LUT for ADD/SUB)",
        sd.lut,
        sg.lut,
        sg.lut - sd.lut
    );
    println!(
        "  Delay: {:.2} → {:.2} ns (Gauss adds {:.2} ns)",
        sd.delay_ns,
        sg.delay_ns,
        sg.delay_ns - sd.delay_ns
    );

    // ---- After union: e-graph discovers both ----
    println!("\n===== AFTER E-GRAPH UNION =====\n");

    let mut eg = EGraph::new();
    let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
    let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
    let c = eg.add(ENode::leaf_typed(AtomOp::Var(2), dt));
    let d = eg.add(ENode::leaf_typed(AtomOp::Var(3), dt));

    let root_direct = build_direct(&mut eg, a, b, c, d, dt);
    let root_gauss = build_gauss(&mut eg, a, b, c, d, dt);
    eg.union(root_gauss, root_direct);

    let t0 = Instant::now();
    let iters = eg.saturate(50, 30000);
    println!(
        "E-graph: {iters} iters, {} classes, {:.3}s\n",
        eg.n_classes(),
        t0.elapsed().as_secs_f64()
    );

    println!(
        "{:<25} {:>8} {:>8} {:>8} {:>10} {:>10} {:>8}",
        "Extraction Mode", "Delay(ns)", "LUT", "DSP", "FF", "Fmax(MHz)", "Shared?"
    );
    println!("{:-<88}", "");

    let modes = [
        ("MinDelay (DP)", ExtractMode::MinDelay, false),
        ("MinDelay (shared)", ExtractMode::MinDelay, true),
        (
            "MinDsp@6ns (DP)",
            ExtractMode::MinDsp { max_delay_ns: 6.0 },
            false,
        ),
        (
            "MinDsp@6ns (shared)",
            ExtractMode::MinDsp { max_delay_ns: 6.0 },
            true,
        ),
        (
            "DSP*10 (DP)",
            ExtractMode::Weighted {
                w_delay: 0.0,
                w_lut: 0.0,
                w_dsp: 10.0,
                w_ff: 0.0,
            },
            false,
        ),
        (
            "DSP*10 (shared)",
            ExtractMode::Weighted {
                w_delay: 0.0,
                w_lut: 0.0,
                w_dsp: 10.0,
                w_ff: 0.0,
            },
            true,
        ),
    ];

    for (name, mode, shared_aware) in &modes {
        let (_, s) = if *shared_aware {
            eg.extract_shared_aware(root_direct, *mode)
        } else {
            eg.extract_optimal(root_direct, *mode)
        };
        println!(
            "{:<25} {:>8.2} {:>8.1} {:>8.1} {:>10.1} {:>10.0} {:>8}",
            name,
            s.delay_ns,
            s.lut,
            s.dsp,
            s.ff,
            s.fmax_mhz,
            if *shared_aware { "✓" } else { "" }
        );
    }

    // Also show raw forms with sharing-aware
    println!("\n{:=<88}", "");
    println!("  Raw form comparison (sharing-aware):");
    let (_, sd_s) = eg1.extract_shared_aware(root_d, ExtractMode::MinDelay);
    let (_, sg_s) = eg2.extract_shared_aware(root_g, ExtractMode::MinDelay);
    println!(
        "    Direct: {:.1} DSP | Gauss: {:.1} DSP | Gauss saves {:.1} DSP",
        sd_s.dsp,
        sg_s.dsp,
        sd_s.dsp - sg_s.dsp
    );
    println!("    ⚠ After union, DP picks Direct (3.70ns) because it can't see sharing benefit.");
    println!("    ILP extraction (ROVER/e-boost) would correctly pick Gauss under DSP constraint.");

    // Pareto
    let pareto = eg.extract_pareto(root_direct);
    println!("\nPareto frontier (DP): {} alternatives", pareto.len());
    for (i, (n, s)) in pareto.iter().enumerate() {
        println!(
            "  {}. {:?} | {:.2}ns | LUT={:.1} DSP={:.1} | {:.0}MHz",
            i + 1,
            n.op,
            s.delay_ns,
            s.lut,
            s.dsp,
            s.fmax_mhz
        );
    }

    // Show sharing-aware cost for Pareto entries
    println!("\n  Same Pareto entries — sharing-aware costs:");
    for (i, (n, _)) in pareto.iter().enumerate() {
        let mut shared = std::collections::HashSet::new();
        let s = compute_shared_dedup(&eg, root_direct, n, &mut shared);
        println!(
            "    {}. {:?} | {:.2}ns | LUT={:.1} DSP={:.1} | {:.0}MHz",
            i + 1,
            n.op,
            s.delay_ns,
            s.lut,
            s.dsp,
            s.fmax_mhz
        );
    }
}

fn compute_shared_dedup(
    eg: &EGraph,
    cid: u32,
    node: &ENode,
    shared: &mut std::collections::HashSet<u32>,
) -> FpgaStats {
    let canonical = eg.canon(cid);
    if !shared.insert(canonical) {
        return FpgaStats::empty();
    }
    let child_stats: Vec<FpgaStats> = node
        .children
        .iter()
        .map(|&ch_cid| {
            let (child_node, _) = eg.extract_optimal(ch_cid, ExtractMode::MinDelay);
            compute_shared_dedup(eg, ch_cid, &child_node, shared)
        })
        .collect();
    FpgaStats::for_node(node.op, &child_stats, &node.dtype)
}
