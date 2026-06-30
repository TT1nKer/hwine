// TCL generator example: generates Vivado synthesis scripts from hwine RTL
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode, DataType};
use hwine_rs::cost::ExtractMode;
use hwine_rs::rtl::generate_rtl;
use hwine_rs::tcl;

fn main() {
    let dt = DataType::S16;

    // DCT 8-point
    let coeffs: [i64; 8] = [181, 251, 213, 142, 256, 107, 71, 25];
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

    let module_name = "bm_dct8";
    let sv_file = format!("{module_name}.sv");
    let rtl = generate_rtl(&eg, root, module_name, 16);
    std::fs::write(&sv_file, &rtl).unwrap();

    let (best, _) = eg.extract_optimal(root, ExtractMode::MinDelay);
    let part = tcl::suggest_part(&eg, &best, 16);
    let tcl_src = tcl::generate_synth_tcl(module_name, &sv_file, part, &format!("{module_name}_report.txt"));
    let tcl_file = format!("synth_{module_name}.tcl");
    std::fs::write(&tcl_file, &tcl_src).unwrap();

    println!("Generated: {sv_file} ({lines} lines), {tcl_file}",
        sv_file = sv_file,
        lines = rtl.lines().count(),
        tcl_file = tcl_file,
    );
    println!("Part: {part}");
    println!("Run: vivado -mode batch -source {tcl_file}", tcl_file = tcl_file);
}
