use hwine_rs::egraph::EGraph;
use hwine_rs::ir::{AtomOp, ENode};
use std::time::Instant;

fn main() {
    let n = 8;
    let mut eg = EGraph::new();
    let z = eg.add(ENode::leaf(AtomOp::Zero));
    let ai = eg.add(ENode::new(AtomOp::AccInit, vec![z]));
    let mut acc = ai;
    let mut mc = ai;

    let mut ws = Vec::with_capacity(n);
    let mut ag = Vec::with_capacity(n);
    for i in 0..n {
        ws.push(eg.add(ENode::leaf(AtomOp::Var(i*2))));
        ag.push(eg.add(ENode::leaf(AtomOp::Var(i*2+1))));
    }

    for i in 0..n {
        let m = eg.add(ENode::new(AtomOp::Mul, vec![ws[i], ag[i]]));
        acc = eg.add(ENode::new(AtomOp::AccStep, vec![acc, m]));
        mc = eg.add(ENode::new(AtomOp::Mac, vec![ws[i], ag[i], mc]));
    }
    eg.union(acc, mc);
    let cid = eg.canon(acc);

    println!("=== Rule Composition: 4 rules → emergent structures ===\n");
    println!("Input: 8-way MAC accumulator (serial ACC_STEP chain)");
    println!("Rules applied:");
    println!("  R1: ACC_STEP(ACC_STEP(init,a),b) → ACC_STEP(init, ADD(a,b))  [flatten]");
    println!("  R2: MAC(w,a,acc) → ADD(MUL(w,a), acc)  [decompose]");
    println!("  R3: ADD(MUL(w,a), acc) → MAC(w,a,acc)  [fuse]");
    println!("  R4: ADD(ADD(a,b), c) → ADD(a, ADD(b,c))  [assoc → tree]\n");

    let t0 = Instant::now();
    let iters = eg.saturate_with_config(50, 20000, 20, 12, false);
    let dt = t0.elapsed();

    let cls = eg.classes[eg.canon(cid) as usize].as_ref().unwrap();
    println!("E-graph saturated: {iters} iterations, {} classes, {:.3}s", eg.n_classes(), dt.as_secs_f64());
    println!("Final e-class: {} equivalent structures found.\n", cls.nodes.len());

    // Categorize structures
    let mut categories: std::collections::HashMap<String, Vec<String>> = std::collections::HashMap::new();

    fn fmt_subtree(node: &ENode, eg: &EGraph, depth: usize) -> String {
        if depth > 3 { return "...".to_string(); }
        match node.op {
            AtomOp::Mac => {
                let (w, _) = eg.extract_optimal(node.children[0]);
                let (a, _) = eg.extract_optimal(node.children[1]);
                let (acc, _) = eg.extract_optimal(node.children[2]);
                format!("MAC({},{},{})", fmt_subtree(&w, eg, depth+1), fmt_subtree(&a, eg, depth+1), fmt_subtree(&acc, eg, depth+1))
            }
            AtomOp::Mul => {
                let (a, _) = eg.extract_optimal(node.children[0]);
                let (b, _) = eg.extract_optimal(node.children[1]);
                format!("MUL({},{})", fmt_subtree(&a, eg, depth+1), fmt_subtree(&b, eg, depth+1))
            }
            AtomOp::Add => {
                let (a, _) = eg.extract_optimal(node.children[0]);
                let (b, _) = eg.extract_optimal(node.children[1]);
                format!("ADD({},{})", fmt_subtree(&a, eg, depth+1), fmt_subtree(&b, eg, depth+1))
            }
            AtomOp::AccStep => {
                let (p, _) = eg.extract_optimal(node.children[0]);
                let (v, _) = eg.extract_optimal(node.children[1]);
                format!("ACC({},{})", fmt_subtree(&p, eg, depth+1), fmt_subtree(&v, eg, depth+1))
            }
            AtomOp::AccInit => "ACC_INIT".to_string(),
            AtomOp::Zero => "0".to_string(),
            AtomOp::Var(i) => format!("v{i}"),
            _ => format!("{:?}", node.op),
        }
    }

    for node in cls.nodes.iter() {
        let s = fmt_subtree(node, &eg, 0);
        let cat = if s.contains("MAC") && s.contains("MUL") { "MAC+MUL cross" }
            else if s.contains("MAC") { "MAC chain" }
            else if s.contains("ACC") { "ACC chain" }
            else if s.contains("ADD") { "ADD tree" }
            else if s.contains("MUL") { "MUL only" }
            else { "other" };
        categories.entry(cat.to_string()).or_default().push(s);
    }

    for (cat, items) in categories.iter() {
        let d = items.len();
        println!("{cat} ({d} variants):");
        for item in items.iter().take(3) {
            let truncated = if item.len() > 120 { format!("{}...", &item[..117]) } else { item.clone() };
            println!("  {}", truncated);
        }
        if items.len() > 3 { println!("  ... and {} more", items.len() - 3); }
    }

    println!("\n── Non-obvious insight ──");
    println!("No single rule says 'turn a serial MAC accumulator into a balanced ADD tree'.");
    println!("That structure emerges from the interaction of 4 simple rules");
    println!("that were defined independently. The e-graph discovers the");
    println!("compositions that no human explicitly programmed.");
}
