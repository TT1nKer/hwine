//! Small FIR dot product with explicit, balanced pipelining.
use hwine_rs::{
    cost::ExtractMode,
    egraph::EGraph,
    ir::{AtomOp, DataType, ENode},
    rtl::{Pipeline, try_generate},
};
fn main() -> Result<(), Box<dyn std::error::Error>> {
    let mut eg = EGraph::new();
    let mut terms = Vec::new();
    for (i, coefficient) in [7, 13, -5].into_iter().enumerate() {
        let x = eg.add(ENode::leaf_typed(AtomOp::Var(i), DataType::S16));
        let c = eg.add(ENode::leaf_typed(AtomOp::Const(coefficient), DataType::S16));
        terms.push(eg.add(ENode::new(AtomOp::Mul, vec![x, c], DataType::S16)));
    }
    let sum = eg.add(ENode::new(
        AtomOp::Add,
        vec![terms[0], terms[1]],
        DataType::S16,
    ));
    let root = eg.add(ENode::new(AtomOp::Add, vec![sum, terms[2]], DataType::S16));
    eg.saturate(12, 5000);
    let rtl = try_generate(
        &eg,
        root,
        "fir3",
        16,
        ExtractMode::MinDelay,
        Pipeline::EveryOp,
    )?;
    std::fs::write("fir3.sv", &rtl.verilog)?;
    println!(
        "fir3.sv: latency {} cycles, one tap tuple per cycle; estimated delay {:.2} (not measured ns)",
        rtl.latency, rtl.estimated.delay_ns
    );
    Ok(())
}
