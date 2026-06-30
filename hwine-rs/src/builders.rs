use crate::egraph::EGraph;
use crate::ir::{AtomOp, ENode, DataType};

/// Build a vector of N variable leaf nodes
pub fn build_vars(eg: &mut EGraph, n: usize) -> Vec<u32> {
    (0..n).map(|i| eg.add(ENode::leaf(AtomOp::Var(i)))).collect()
}

/// Build a serial chain: v0 + v1 + v2 + ... + v{n-1}
pub fn build_add_chain(eg: &mut EGraph, n: usize) -> u32 {
    let vars = build_vars(eg, n);
    let mut chain = vars[0];
    for i in 1..n {
        chain = eg.add(ENode::new(AtomOp::Add, vec![chain, vars[i]], DataType::default()));
    }
    chain
}

/// Build a balanced addition tree recursively
pub fn build_balanced_add_tree(eg: &mut EGraph, n: usize) -> u32 {
    fn balanced(eg: &mut EGraph, cids: &[u32]) -> u32 {
        if cids.len() == 1 {
            return cids[0];
        }
        let mid = cids.len() / 2;
        let left = balanced(eg, &cids[..mid]);
        let right = balanced(eg, &cids[mid..]);
        eg.add(ENode::new(AtomOp::Add, vec![left, right], DataType::default()))
    }
    let vars = build_vars(eg, n);
    balanced(eg, &vars)
}

/// Build a serial MAC chain
pub fn build_mac_chain(eg: &mut EGraph, n: usize, full: bool) -> u32 {
    let ws = build_vars(eg, n * 2); // even indices: w, odd: a
    let zero = eg.add(ENode::leaf(AtomOp::Zero));
    let mut acc = eg.add(ENode::new(AtomOp::AccInit, vec![zero], DataType::default()));
    for i in 0..n {
        let m = eg.add(ENode::new(AtomOp::Mul, vec![ws[i*2], ws[i*2+1]], DataType::default()));
        if full {
            acc = eg.add(ENode::new(AtomOp::Mac, vec![ws[i*2], ws[i*2+1], acc], DataType::default()));
        } else {
            acc = eg.add(ENode::new(AtomOp::AccStep, vec![acc, m], DataType::default()));
        }
    }
    acc
}
