//! Finite, immutable extraction plans. Children are the actual choices costed
//! with the parent; RTL emission never re-runs extraction at each child.
use std::collections::{BTreeSet, HashMap};
use std::rc::Rc;

use crate::cost::{ExtractMode, FpgaStats};
use crate::egraph::EGraph;
use crate::error::{HwineError, HwineResult};
use crate::ir::ENode;

#[derive(Debug, Clone)]
pub struct Plan {
    pub node: ENode,
    pub children: Vec<Rc<Plan>>,
    pub stats: FpgaStats,
}

impl EGraph {
    /// A bounded relaxation over reachable classes. Each candidate captures
    /// already finite child plans. Strict improvement prevents zero-cost cycles.
    /// This is a heuristic tree-cost search, not globally optimal DAG mapping.
    pub fn extract_plan(&self, root: u32, mode: ExtractMode) -> HwineResult<Rc<Plan>> {
        let weights = match mode {
            ExtractMode::Weighted {
                w_delay,
                w_lut,
                w_dsp,
                w_ff,
            } => vec![w_delay, w_lut, w_dsp, w_ff],
            ExtractMode::MinLut { max_delay_ns }
            | ExtractMode::MinDsp { max_delay_ns }
            | ExtractMode::MinFf { max_delay_ns } => vec![max_delay_ns],
            _ => vec![],
        };
        if weights.iter().any(|v| !v.is_finite() || *v < 0.0) {
            return Err(HwineError::InvalidInput(
                "extraction weights/limits must be finite and nonnegative",
            ));
        }
        let mut pending = vec![root];
        let mut reachable = BTreeSet::new();
        while let Some(cid) = pending.pop() {
            let nodes = self.class_nodes(cid).ok_or(HwineError::InvalidClass(cid))?;
            let cid = self.canon(cid);
            if !reachable.insert(cid) {
                continue;
            }
            for n in nodes {
                pending.extend(n.children.iter().copied());
            }
        }
        let mut best: HashMap<u32, Rc<Plan>> = HashMap::new();
        for _ in 0..=reachable.len() {
            let mut changed = false;
            for &cid in &reachable {
                for node in self.class_nodes(cid).unwrap() {
                    let children: Option<Vec<_>> = node
                        .children
                        .iter()
                        .map(|&c| best.get(&self.canon(c)).cloned())
                        .collect();
                    let Some(children) = children else {
                        continue;
                    };
                    let child_stats: Vec<_> = children.iter().map(|p| p.stats.clone()).collect();
                    let stats = FpgaStats::for_node(node.op, &child_stats, &node.dtype);
                    let cost = stats.scalar_cost(mode);
                    if cost.is_finite()
                        && best
                            .get(&cid)
                            .is_none_or(|p| cost < p.stats.scalar_cost(mode))
                    {
                        best.insert(
                            cid,
                            Rc::new(Plan {
                                node: node.clone(),
                                children,
                                stats,
                            }),
                        );
                        changed = true;
                    }
                }
            }
            if !changed {
                break;
            }
        }
        best.remove(&self.canon(root)).ok_or_else(|| {
            HwineError::ExtractionFailed(
                "no finite acyclic plan satisfies the extraction constraints".into(),
            )
        })
    }
}
