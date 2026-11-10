use hwine_rs::cost::{ExtractMode, FpgaStats, delay_ns};
use hwine_rs::egraph::EGraph;
use hwine_rs::error::HwineError;
use hwine_rs::ir::{AtomOp, DataType, ENode, OverflowMode};
use hwine_rs::rtl::{Pipeline, RtlGen, try_generate, try_generate_rtl};

fn var(eg: &mut EGraph, i: usize, t: DataType) -> u32 {
    eg.add(ENode::leaf_typed(AtomOp::Var(i), t))
}

#[test]
fn unsupported_atoms_are_errors_even_when_they_used_to_pass_through() {
    for op in [
        AtomOp::Slice,
        AtomOp::Extract,
        AtomOp::Pack,
        AtomOp::Unpack,
        AtomOp::Quant,
        AtomOp::Dequant,
        AtomOp::DequantW,
        AtomOp::Sat,
        AtomOp::Round,
        AtomOp::Route,
        AtomOp::Broadcast,
        AtomOp::Concat,
        AtomOp::Div,
        AtomOp::Exp,
        AtomOp::Softmax,
        AtomOp::Scan,
        AtomOp::Delay,
        AtomOp::Buffer,
        AtomOp::StrLit,
        AtomOp::StreamRead,
        AtomOp::StreamWrite,
        AtomOp::StreamFifo,
        AtomOp::AccInit,
        AtomOp::AccStep,
        AtomOp::AccRead,
        AtomOp::AccReset,
    ] {
        let mut eg = EGraph::new();
        let a = var(&mut eg, 0, DataType::U16);
        let root = eg.add(ENode::new(op, vec![a; op.arity()], DataType::U16));
        assert_eq!(
            try_generate_rtl(&eg, root, "dut", 16),
            Err(HwineError::UnsupportedRtlOp(op))
        );
    }
}

#[test]
fn malformed_arity_is_not_filled_with_zero() {
    for count in [0, 1, 3] {
        let mut eg = EGraph::new();
        let a = var(&mut eg, 0, DataType::U16);
        let root = eg.add(ENode::new(AtomOp::Add, vec![a; count], DataType::U16));
        eg.saturate(3, 100);
        assert!(try_generate_rtl(&eg, root, "dut", 16).is_err());
        assert!(
            eg.try_add(ENode::new(AtomOp::Add, vec![a; count], DataType::U16))
                .is_err()
        );
    }
}

#[test]
fn wrong_types_and_widths_fail_closed() {
    for bad in [
        DataType::U8,
        DataType::S16,
        DataType {
            width: 0,
            ..DataType::U16
        },
        DataType {
            width: 65,
            ..DataType::U16
        },
        DataType {
            overflow: OverflowMode::Sat,
            ..DataType::U16
        },
        DataType {
            overflow: OverflowMode::Wide,
            ..DataType::U16
        },
    ] {
        let mut eg = EGraph::new();
        let a = var(&mut eg, 0, bad);
        let z = eg.add(ENode::leaf_typed(AtomOp::Zero, DataType::U16));
        let root = eg.add(ENode::new(AtomOp::Add, vec![a, z], DataType::U16));
        eg.saturate(3, 100);
        assert!(try_generate_rtl(&eg, root, "dut", 16).is_err());
    }
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U8);
    assert!(try_generate_rtl(&eg, a, "dut", 16).is_err());
    assert!(try_generate_rtl(&eg, u32::MAX, "dut", 8).is_err());
}

#[test]
fn rewrites_do_not_merge_mixed_precision_or_saturating_arithmetic() {
    for t in [
        DataType::U8,
        DataType {
            overflow: OverflowMode::Sat,
            ..DataType::U16
        },
    ] {
        let mut eg = EGraph::new();
        let a = var(&mut eg, 0, t);
        let b = var(&mut eg, 1, t);
        let c = var(&mut eg, 2, DataType::U16);
        let ab = eg.add(ENode::new(AtomOp::Add, vec![a, b], t));
        let root = eg.add(ENode::new(AtomOp::Mul, vec![ab, c], DataType::U16));
        eg.saturate(10, 1000);
        assert_eq!(eg.class_nodes(root).unwrap().len(), 1);
    }
}

#[test]
fn signed_shift_counts_are_rejected() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::S16);
    let c = eg.add(ENode::leaf_typed(AtomOp::Const(-1), DataType::S16));
    let root = eg.add(ENode::new(AtomOp::Shr, vec![a, c], DataType::S16));
    assert!(try_generate_rtl(&eg, root, "dut", 16).is_err());
}

#[test]
fn branch_latency_mismatch_is_rejected() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U16);
    let b = var(&mut eg, 1, DataType::U16);
    let delayed = eg.add(ENode::new(AtomOp::Pipe, vec![a], DataType::U16));
    let root = eg.add(ENode::new(AtomOp::Add, vec![delayed, b], DataType::U16));
    assert!(try_generate_rtl(&eg, root, "dut", 16).is_err());
    let b = eg.add(ENode::new(AtomOp::Pipe, vec![b], DataType::U16));
    let aligned = eg.add(ENode::new(AtomOp::Add, vec![delayed, b], DataType::U16));
    let out = try_generate(
        &eg,
        aligned,
        "dut",
        16,
        ExtractMode::MinDelay,
        Pipeline::None,
    )
    .unwrap();
    assert_eq!(out.latency, 1);
    assert!(
        try_generate(
            &eg,
            aligned,
            "dut",
            16,
            ExtractMode::MinDelay,
            Pipeline::EveryOp
        )
        .is_err()
    );
}

#[test]
fn register_does_not_erase_the_critical_path_before_it() {
    let dt = DataType::U16;
    let mul = FpgaStats::for_node(AtomOp::Mul, &[FpgaStats::empty(), FpgaStats::empty()], &dt);
    let pipe = FpgaStats::for_node(AtomOp::Pipe, std::slice::from_ref(&mul), &dt);
    let add = FpgaStats::for_node(AtomOp::Add, &[pipe.clone(), pipe.clone()], &dt);
    assert_eq!(pipe.delay_ns, mul.delay_ns);
    assert_eq!(pipe.output_delay_ns, delay_ns(AtomOp::Pipe, &dt));
    assert_eq!(
        add.delay_ns,
        mul.delay_ns
            .max(pipe.output_delay_ns + delay_ns(AtomOp::Add, &dt))
    );
}

#[test]
fn shared_resource_accounting_preserves_timing() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U16);
    let b = var(&mut eg, 1, DataType::U16);
    let ab = eg.add(ENode::new(AtomOp::Mul, vec![a, b], DataType::U16));
    let root = eg.add(ENode::new(AtomOp::Add, vec![ab, ab], DataType::U16));
    let (_, tree) = eg.extract_optimal(root, ExtractMode::MinDelay);
    let (_, shared) = eg.extract_shared_aware(root, ExtractMode::MinDelay);
    assert_eq!(shared.delay_ns, tree.delay_ns);
    assert_eq!(shared.cycles, tree.cycles);
    assert_eq!(shared.dsp, tree.dsp / 2.0);
}

#[test]
fn impossible_extraction_does_not_become_constant_zero() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U16);
    let root = eg.add(ENode::new(AtomOp::Add, vec![a, a], DataType::U16));
    assert!(
        eg.try_extract_optimal(root, ExtractMode::MinLut { max_delay_ns: 0.0 })
            .is_err()
    );
    assert!(
        eg.try_extract_optimal(u32::MAX, ExtractMode::MinDelay)
            .is_err()
    );
    assert!(
        eg.extract_plan(
            root,
            ExtractMode::Weighted {
                w_delay: -1.0,
                w_lut: 0.0,
                w_dsp: 0.0,
                w_ff: 0.0
            }
        )
        .is_err()
    );
}

#[test]
fn merged_child_alias_remains_valid() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U16);
    let z = eg.add(ENode::leaf_typed(AtomOp::Zero, DataType::U16));
    let root = eg.add(ENode::new(AtomOp::Add, vec![a, z], DataType::U16));
    eg.union(a, root);
    assert!(
        eg.try_add(ENode::new(AtomOp::Pipe, vec![root], DataType::U16))
            .is_ok()
    );
}

#[test]
fn name_conflicts_return_errors_without_panics_or_partial_output() {
    let mut eg = EGraph::new();
    let a = var(&mut eg, 0, DataType::U16);
    let b = var(&mut eg, 1, DataType::U16);
    let root = eg.add(ENode::new(AtomOp::Add, vec![a, b], DataType::U16));
    let mut genr = RtlGen::new("dut", 16);
    genr.set_name(a, "same");
    genr.set_name(b, "same");
    assert!(matches!(
        genr.emit_node(&eg, root, true, &mut Default::default()),
        Err(HwineError::PortConflict { .. })
    ));
    for bad in ["module", "bad;endmodule", "result", "clk", "hwine_n0"] {
        genr.set_name(a, bad);
        genr.set_name(b, "good");
        assert!(
            genr.emit_node(&eg, root, true, &mut Default::default())
                .is_err()
        );
    }
}

#[test]
fn grouped_pipeline_handles_shared_and_uneven_paths_and_rejects_zero() {
    let mut eg = EGraph::new();
    let dt = DataType::S16;
    let a = var(&mut eg, 0, dt);
    let b = var(&mut eg, 1, dt);
    let ab = eg.add(ENode::new(AtomOp::Mul, vec![a, b], dt));
    let sum = eg.add(ENode::new(AtomOp::Add, vec![ab, a], dt));
    let root = eg.add(ENode::new(AtomOp::Sub, vec![sum, ab], dt));
    for (n, latency) in [(1, 3), (2, 2), (3, 1), (usize::MAX, 1)] {
        let rtl = try_generate(
            &eg,
            root,
            "dut",
            16,
            ExtractMode::MinDelay,
            Pipeline::EveryN(n),
        )
        .unwrap();
        assert_eq!(rtl.latency, latency);
    }
    assert!(
        try_generate(
            &eg,
            root,
            "dut",
            16,
            ExtractMode::MinDelay,
            Pipeline::EveryN(0)
        )
        .is_err()
    );
}
