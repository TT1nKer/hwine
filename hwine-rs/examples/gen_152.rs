use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::{generate_rtl, generate_pipelined_rtl};
use std::fs;
fn main() {
    let n = 152;
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n { vs.push(eg.add(ENode::leaf(AtomOp::Var(i)))); }
    let mut c = vs[0];
    for i in 1..n { c = eg.add(ENode::new(AtomOp::Add, vec![c, vs[i]])); }
    let rtl_s = generate_rtl(&eg, c, "serial_fir_152", 16);
    eg.saturate_with_config(30, 5000, 15, 10, false);
    let rtl_p = generate_pipelined_rtl(&eg, c, "pipe_fir_152", 16);
    fs::write("rtl_serial_fir_152.sv", &rtl_s).unwrap();
    fs::write("rtl_pipe_fir_152.sv", &rtl_p).unwrap();
    println!("serial: {} lines, pipe: {} lines", rtl_s.lines().count(), rtl_p.lines().count());
}
