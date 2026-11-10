use crate::cost::ExtractMode;
use crate::egraph::EGraph;
use crate::ir::ENode;

/// Recursively compute the maximum depth of an extracted e-node tree.
pub fn extracted_tree_depth(eg: &EGraph, node: &ENode, mode: ExtractMode) -> usize {
    if node.children.is_empty() {
        return 0;
    }
    1 + node
        .children
        .iter()
        .map(|&c| {
            let (child_node, _) = eg.extract_optimal(c, mode);
            extracted_tree_depth(eg, &child_node, mode)
        })
        .max()
        .unwrap_or(0)
}
