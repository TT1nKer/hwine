use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_rtl;
use std::fs;

fn main() {
    let n = 16;
    let dw = 16; // 16-bit to avoid overflow for int4×int8×16

    let mut eg = EGraph::new();
    let mut ws = Vec::with_capacity(n);
    let mut ag = Vec::with_capacity(n);
    for i in 0..n {
        ws.push(eg.add(ENode::leaf(AtomOp::Var(i * 2))));
        ag.push(eg.add(ENode::leaf(AtomOp::Var(i * 2 + 1))));
    }
    let mut muls = Vec::with_capacity(n);
    for i in 0..n {
        muls.push(eg.add(ENode::new(
            AtomOp::Mul,
            vec![ws[i], ag[i]],
            DataType::default(),
        )));
    }
    let mut chain = muls[0];
    for i in 1..n {
        chain = eg.add(ENode::new(
            AtomOp::Add,
            vec![chain, muls[i]],
            DataType::default(),
        ));
    }

    eg.saturate_with_config(50, 20000, 15, 10, false);

    let rtl = generate_rtl(&eg, chain, &format!("mac_tile_{n}_{dw}b"), dw);
    fs::write("mac_tile_16_16b.sv", &rtl).unwrap();

    let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    fn depth(n: &ENode, eg: &EGraph) -> usize {
        if n.children.is_empty() {
            0
        } else {
            1 + n
                .children
                .iter()
                .map(|&c| depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
                .max()
                .unwrap_or(0)
        }
    }
    println!(
        "Generated mac_tile_16_16b.sv: {} bits, depth={}lv, {} lines",
        dw,
        depth(&best, &eg),
        rtl.lines().count()
    );
}
