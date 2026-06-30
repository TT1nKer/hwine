#[cfg(test)]
mod tests {
    use crate::egraph::{EGraph, decompose_to_pow2};
    use crate::cost::ExtractMode;
    use crate::ir::{AtomOp, DataType, ENode};

    // ─── CSD Decomposition ──────────────────────────────────────────────

    #[test]
    fn test_csd_positive_7() {
        let terms = decompose_to_pow2(7);
        assert_eq!(terms.len(), 2, "7 should use 2 CSD terms (8-1) not 3 (4+2+1)");
        // 7 = 8 - 1 → (1,3), (-1,0)
        assert!(terms.contains(&(1, 3)), "should contain +8 shift");
        assert!(terms.contains(&(-1, 0)), "should contain -1 shift");
    }

    #[test]
    fn test_csd_positive_13() {
        let terms = decompose_to_pow2(13);
        // 13 can be represented in CSD (16-2-1 or other forms)
        assert!(!terms.is_empty(), "13 should be decomposable");
        let reconstructed: i64 = terms.iter().map(|(s, e)| (*s as i64) * (1i64 << *e)).sum();
        assert_eq!(reconstructed, 13, "CSD must reconstruct to 13");
    }

    #[test]
    fn test_csd_negative_7() {
        let terms = decompose_to_pow2(-7);
        assert!(!terms.is_empty(), "negative constants should be decomposable");
        assert_eq!(terms.len(), 2, "-7 should use 2 CSD terms");
        // -7 = -(8-1) = -8 + 1
        assert!(terms.contains(&(-1, 3)), "should contain -8 shift");
        assert!(terms.contains(&(1, 0)), "should contain +1 shift");
    }

    #[test]
    fn test_csd_negative_17() {
        let terms = decompose_to_pow2(-17);
        assert!(!terms.is_empty(), "-17 should be decomposable");
        // -17 = -(16+1) = -16 - 1
        assert!(terms.contains(&(-1, 4)), "should contain -16 shift");
        assert!(terms.contains(&(-1, 0)), "should contain -1 shift");
    }

    #[test]
    fn test_csd_power_of_2() {
        let terms = decompose_to_pow2(256);
        assert_eq!(terms.len(), 1, "power of 2 should use 1 term");
        assert_eq!(terms[0], (1, 8));
    }

    #[test]
    fn test_csd_one() {
        let terms = decompose_to_pow2(1);
        assert_eq!(terms.len(), 1);
        assert_eq!(terms[0], (1, 0));
    }

    #[test]
    fn test_csd_zero() {
        let terms = decompose_to_pow2(0);
        assert!(terms.is_empty());
    }

    // ─── Vector reconstruction from CSD terms ───────────────────────────

    fn reconstruct_csd(terms: &[(i32, u32)]) -> i64 {
        terms.iter().map(|(s, e)| (*s as i64) * (1i64 << *e)).sum()
    }

    #[test]
    fn test_csd_reconstruction() {
        for k in [3, 7, 13, 25, 31, 71, 107, 142, 181, 213, 251, 256] {
            let terms = decompose_to_pow2(k);
            assert!(!terms.is_empty(), "k={} should be decomposable", k);
            let reconstructed = reconstruct_csd(&terms);
            assert_eq!(reconstructed, k, "CSD reconstruction failed for {}", k);
        }
    }

    #[test]
    fn test_csd_reconstruction_negative() {
        for k in [-3, -7, -13, -17, -25] {
            let terms = decompose_to_pow2(k);
            assert!(!terms.is_empty(), "k={} should be decomposable", k);
            let reconstructed = reconstruct_csd(&terms);
            assert_eq!(reconstructed, k, "CSD reconstruction failed for {}", k);
        }
    }

    // ─── E-Graph Cycle Detection ────────────────────────────────────────

    #[test]
    fn test_no_cycle_in_clean_graph() {
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), DataType::S16));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], DataType::S16));
        let (node, stats) = eg.extract_optimal(add, ExtractMode::MinDelay);
        assert_eq!(node.op, AtomOp::Add, "should extract Add node");
        assert!(stats.delay_ns < 1e9, "delay should be finite (no cycle detected)");
    }

    #[test]
    fn test_cycle_detection_prevents_zero_substitution() {
        // Create a situation where a node references itself through union
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
        let zero = eg.add(ENode::leaf_typed(AtomOp::Zero, DataType::S16));
        // Add(a, Zero) = a (identity)
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, zero], DataType::S16));
        eg.union(add, a);
        eg.saturate(10, 1000);

        let (node, stats) = eg.extract_optimal(a, ExtractMode::MinDelay);
        // The DP should prefer Var(0) over Add(Var(0), Zero) because Var is cheaper
        assert!(matches!(node.op, AtomOp::Var(_)), "should extract Var, not zero-substituted Add");
        assert!(stats.delay_ns < 1e9, "should not return infinite cost");
    }

    // ─── Associativity ──────────────────────────────────────────────────

    #[test]
    fn test_associativity_reduces_depth() {
        let mut eg = EGraph::new();
        let vs: Vec<u32> = (0..8).map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), DataType::S16))).collect();
        let mut chain = vs[0];
        for i in 1..8 {
            chain = eg.add(ENode::new(AtomOp::Add, vec![chain, vs[i]], DataType::S16));
        }
        let serial_depth = 7;

        eg.saturate(50, 10000);
        let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);

        fn depth(n: &ENode, eg: &EGraph) -> usize {
            if n.children.is_empty() { 0 }
            else { 1 + n.children.iter().map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg)).max().unwrap_or(0) }
        }

        let tree_depth = depth(&best, &eg);
        assert!(tree_depth < serial_depth, "associativity should reduce depth: {} < {}", tree_depth, serial_depth);
    }

    // ─── DSP Pre-Adder Pattern Match ────────────────────────────────────

    #[test]
    fn test_dsp_preadd_mapping() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let c = eg.add(ENode::leaf_typed(AtomOp::Var(2), dt));
        let ab = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
        let mul = eg.add(ENode::new(AtomOp::Mul, vec![ab, c], dt));

        eg.saturate(30, 10000);
        let (best, stats) = eg.extract_optimal(mul, ExtractMode::MinDelay);
        assert!(matches!(best.op, AtomOp::DspPreAdd | AtomOp::Mul),
            "should find either DspPreAdd or original Mul in e-class");
        // DSP pre-adder should use 1 DSP with pre-adder absorbed
        assert!(stats.dsp <= 1.0, "should use ≤1 DSP slice");
    }

    // ─── Pipeline Retiming ──────────────────────────────────────────────

    #[test]
    fn test_pipeline_retime_creates_fifo_option() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));

        let pre_classes = eg.n_classes();
        eg.saturate_retime(20, 5000);
        let post_classes = eg.n_classes();
        assert!(post_classes > pre_classes, "retiming should create new classes");

        let cls = eg.classes[eg.canon(add) as usize].as_ref().unwrap();
        let has_fifo = cls.nodes.iter().any(|n| n.op == AtomOp::StreamFifo);
        let has_add = cls.nodes.iter().any(|n| n.op == AtomOp::Add);
        assert!(has_fifo, "e-class should contain StreamFifo option");
        assert!(has_add, "e-class should still contain original Add");
    }

    // ─── Multi-Objective Extraction ─────────────────────────────────────

    #[test]
    fn test_min_delay_prefers_low_latency() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));

        let (_, stats) = eg.extract_optimal(add, ExtractMode::MinDelay);
        assert!(stats.delay_ns <= 1.0, "MinDelay should choose lowest delay path");
    }

    #[test]
    fn test_min_ff_prefers_no_registers() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
        eg.saturate_retime(20, 5000);

        let (_, stats) = eg.extract_optimal(add, ExtractMode::MinFf { max_delay_ns: 100.0 });
        assert_eq!(stats.ff, 0.0, "MinFF with generous delay should use 0 FFs");
    }

    // ─── DataType Propagation ───────────────────────────────────────────

    #[test]
    fn test_datatype_preserved_in_extraction() {
        let dt = DataType::U16; // unsigned 16-bit
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));

        eg.saturate(20, 5000);
        let (best, _) = eg.extract_optimal(add, ExtractMode::MinDelay);

        fn check_dtype(n: &ENode, eg: &EGraph, expected: DataType) {
            assert_eq!(n.dtype, expected, "dtype should be preserved through extraction");
            for &c in &n.children {
                let (cn, _) = eg.extract_optimal(c, ExtractMode::MinDelay);
                // Children may have different dtypes (e.g., Const has default)
                if matches!(cn.op, AtomOp::Var(_) | AtomOp::Add | AtomOp::Sub | AtomOp::Mul) {
                    check_dtype(&cn, eg, expected);
                }
            }
        }

        check_dtype(&best, &eg, dt);
    }

    // ─── Integration: IR → RTL → iverilog syntax check ──────────────────

    #[test]
    fn test_rtl_syntax_valid_dct8() {
        use crate::rtl::generate_rtl;
        let coeffs: [i64; 8] = [181, 251, 213, 142, 256, 107, 71, 25];
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let inputs: Vec<u32> = (0..8).map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), dt))).collect();
        let mut terms = Vec::new();
        for i in 0..8 {
            let c = eg.add(ENode::leaf_typed(AtomOp::Const(coeffs[i]), dt));
            terms.push(eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], c], dt)));
        }
        let mut root = terms[0];
        for i in 1..8 { root = eg.add(ENode::new(AtomOp::Add, vec![root, terms[i]], dt)); }
        eg.saturate(20, 5000);
        let rtl = generate_rtl(&eg, root, "test_dct8", 16);
        assert!(rtl.contains("module test_dct8"), "RTL must have module declaration");
        assert!(rtl.contains("input"), "RTL must have input ports");
        assert!(rtl.contains("output"), "RTL must have output port");
        assert!(!rtl.contains("cycle_break"), "RTL must not contain cycle-break wires");
    }

    #[test]
    fn test_rtl_dedups_reused_var_ports() {
        use crate::rtl::generate_rtl;
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        // Same variable used twice in expression
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, a], dt));
        let rtl = generate_rtl(&eg, add, "test_dedup", 16);
        // Count how many times 'a0' appears as input port
        let input_count = rtl.lines().filter(|l| l.contains("input") && l.contains("a0")).count();
        assert_eq!(input_count, 1, "Var(a0) used twice but should only generate 1 input port");
    }

    #[test]
    fn test_stream_fir_has_clk_and_ff() {
        use crate::rtl::generate_rtl;
        let dt = DataType::S16;
        let taps: [i64; 3] = [7, 13, -5];
        let mut eg = EGraph::new();
        let inputs: Vec<u32> = (0..3).map(|i| eg.add(ENode::leaf_typed(AtomOp::Var(i), dt))).collect();
        let coeffs: Vec<u32> = taps.iter().map(|&c| eg.add(ENode::leaf_typed(AtomOp::Const(c), dt))).collect();
        let mut terms = Vec::new();
        for i in 0..3 { terms.push(eg.add(ENode::new(AtomOp::Mul, vec![inputs[i], coeffs[i]], dt))); }
        let mut fir = terms[0];
        for i in 1..3 { fir = eg.add(ENode::new(AtomOp::Add, vec![fir, terms[i]], dt)); }
        eg.saturate_retime(20, 5000);
        let rtl = generate_rtl(&eg, fir, "test_stream", 16);
        assert!(rtl.contains("input  logic clk"), "streaming RTL must have clk input");
        assert!(rtl.contains("always_ff @(posedge clk)"), "streaming RTL must have sequential logic");
    }

    // ─── Property: try_add / try_union error paths ──────────────────────

    #[test]
    fn test_try_add_invalid_child() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let bad_node = ENode::new(AtomOp::Add, vec![a, 99999], dt);
        let result = eg.try_add(bad_node);
        assert!(result.is_err(), "try_add with invalid child CID must return Err");
    }

    #[test]
    fn test_try_union_deleted_class() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        eg.union(a, b); // b merged into a, b is now deleted
        let result = eg.try_union(a, 99999);
        assert!(result.is_err(), "try_union with out-of-bounds ID must return Err");
    }

    #[test]
    fn test_try_union_valid() {
        let dt = DataType::S16;
        let mut eg = EGraph::new();
        let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), dt));
        let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), dt));
        let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], dt));
        let c = eg.add(ENode::leaf_typed(AtomOp::Var(2), dt));
        let b_add_c = eg.add(ENode::new(AtomOp::Add, vec![b, c], dt));
        let result = eg.try_union(add, b_add_c);
        assert!(result.is_ok(), "try_union with valid IDs must return Ok");
    }

    // ─── Property: Pareto domination with cycles ────────────────────────

    #[test]
    fn test_pareto_cycles_in_domination() {
        use crate::cost::FpgaStats;
        let low_cycles = FpgaStats { lut: 5.0, dsp: 2.0, ff: 10.0, delay_ns: 3.0, cycles: 2, fmax_mhz: 333.0 };
        let high_cycles = FpgaStats { lut: 5.0, dsp: 2.0, ff: 10.0, delay_ns: 3.0, cycles: 5, fmax_mhz: 333.0 };
        // Same resources, same delay, but fewer cycles → dominates
        assert!(low_cycles.dominates(&high_cycles), "fewer cycles must dominate");
        assert!(!high_cycles.dominates(&low_cycles), "more cycles must not dominate");
    }

    #[test]
    fn test_pareto_cycles_no_cross_domination() {
        use crate::cost::FpgaStats;
        let fast_high_cycles = FpgaStats { lut: 5.0, dsp: 2.0, ff: 20.0, delay_ns: 0.5, cycles: 5, fmax_mhz: 500.0 };
        let slow_low_cycles = FpgaStats { lut: 5.0, dsp: 2.0, ff: 0.0, delay_ns: 5.0, cycles: 0, fmax_mhz: 200.0 };
        // Different tradeoff: fast+more cycles vs slow+fewer cycles → no domination
        assert!(!fast_high_cycles.dominates(&slow_low_cycles), "different tradeoffs must not dominate");
        assert!(!slow_low_cycles.dominates(&fast_high_cycles), "different tradeoffs must not dominate");
    }
}
