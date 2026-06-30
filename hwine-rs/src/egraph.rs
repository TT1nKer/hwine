use std::collections::{HashMap, HashSet};
use fxhash::FxBuildHasher;
use crate::ir::{AtomOp, ENode, DataType, OverflowMode};
use crate::cost::{FpgaStats, ExtractMode};
use crate::error::{HwineError, HwineResult};

type FxHashSet<T> = HashSet<T, FxBuildHasher>;
type FxHashMap<K, V> = HashMap<K, V, FxBuildHasher>;

/// An equivalence class of e-nodes
#[derive(Debug, Clone)]
pub struct EClass {
    pub nodes: Vec<ENode>,
}

/// E-graph engine for meta-operation rewriting
pub struct EGraph {
    pub(crate) classes: Vec<Option<EClass>>, // index = e-class ID, None = deleted
    parents: Vec<u32>,                       // union-find parent array
    pub(crate) hashcons: FxHashMap<ENode, u32>,
    pub(crate) changed: Vec<u32>,            // worklist
    parents_of: Vec<FxHashSet<u32>>,         // child → parent tracking
    union_count: u64,
    next_id: u32,
}

impl EGraph {
    pub fn new() -> Self {
        Self {
            classes: Vec::new(),
            parents: Vec::new(),
            hashcons: FxHashMap::default(),
            changed: Vec::new(),
            parents_of: Vec::new(),
            union_count: 0,
            next_id: 0,
        }
    }

    #[inline]
    pub fn canon(&self, mut id: u32) -> u32 {
        while self.parents[id as usize] != id {
            id = self.parents[id as usize];
        }
        id
    }

    #[inline]
    fn canon_mut(&mut self, mut id: u32) -> u32 {
        let root = self.canon(id);
        // Path compression
        while id != root {
            let next = self.parents[id as usize];
            self.parents[id as usize] = root;
            id = next;
        }
        root
    }

    fn alloc_class(&mut self) -> u32 {
        let id = self.next_id;
        self.next_id += 1;
        self.classes.push(Some(EClass { nodes: Vec::new() }));
        while self.parents.len() as u32 <= id {
            self.parents.push(self.parents.len() as u32);
        }
        while self.parents_of.len() as u32 <= id {
            self.parents_of.push(FxHashSet::default());
        }
        self.changed.push(id);
        id
    }

    /// Add a node to the e-graph. Returns canonical e-class ID.
    ///
    /// # Examples
    ///
    /// ```
    /// use hwine_rs::egraph::EGraph;
    /// use hwine_rs::ir::{AtomOp, ENode, DataType};
    ///
    /// let mut eg = EGraph::new();
    /// let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
    /// let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), DataType::S16));
    /// let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], DataType::S16));
    /// ```
    pub fn add(&mut self, mut node: ENode) -> u32 {
        // Canonicalize children
        node.children = node
            .children
            .iter()
            .map(|&c| self.canon_mut(c))
            .collect();

        // Hashcons check
        if let Some(&existing) = self.hashcons.get(&node) {
            return self.canon_mut(existing);
        }

        let cid = self.alloc_class();
        self.classes[cid as usize].as_mut().unwrap().nodes.push(node.clone());
        self.hashcons.insert(node.clone(), cid);

        // Register parent relationships
        for &child in node.children.iter() {
            self.parents_of[child as usize].insert(cid);
        }

        cid
    }

    /// Fallible variant of `add`: returns HwineError on invalid input.
    /// Validates child CIDs bounds before canonicalization (avoids panic on OOB).
    pub fn try_add(&mut self, mut node: ENode) -> HwineResult<u32> {
        // Validate children BEFORE canonicalize (avoids OOB panic)
        for &c in &node.children {
            if c as usize >= self.classes.len() || self.classes[c as usize].is_none() {
                return Err(HwineError::InvalidClass(c));
            }
        }
        node.children = node.children.iter().map(|&c| self.canon_mut(c)).collect();
        if node.children.iter().any(|&c| self.classes.get(c as usize).is_none()) {
            return Err(HwineError::InvalidInput("child class deleted or invalid"));
        }
        if let Some(&existing) = self.hashcons.get(&node) {
            return Ok(self.canon_mut(existing));
        }
        let cid = self.alloc_class();
        self.classes[cid as usize].as_mut().unwrap().nodes.push(node.clone());
        self.hashcons.insert(node.clone(), cid);
        for &child in node.children.iter() {
            self.parents_of[child as usize].insert(cid);
        }
        Ok(cid)
    }

    /// Add a leaf node (no children)
    pub fn add_leaf(&mut self, op: AtomOp) -> u32 {
        self.add(ENode::leaf(op))
    }

    /// Merge e-class b into a. Returns canonical id.
    pub fn union(&mut self, a: u32, b: u32) -> u32 {
        let a = self.canon_mut(a);
        let b = self.canon_mut(b);
        if a == b {
            return a;
        }

        self.parents[b as usize] = a;
        self.union_count += 1;

        // Move nodes from b to a
        let b_nodes = {
            let b_class = self.classes[b as usize].take().unwrap();
            b_class.nodes
        };
        self.classes[a as usize].as_mut().unwrap().nodes.extend(b_nodes);

        // Track changed
        self.changed.push(a);

        // Transfer parent tracking
        let b_parents: Vec<u32> = self.parents_of[b as usize].drain().collect();
        for p in b_parents {
            self.parents_of[a as usize].insert(p);
        }

        // Repair parents
        self.repair_parents(a);

        a
    }

    /// Fallible variant of `union`: validates both e-class IDs before merging.
    /// Boundaries are checked BEFORE canonicalize to avoid OOB panic.
    pub fn try_union(&mut self, a: u32, b: u32) -> HwineResult<u32> {
        // Validate raw IDs before canonicalize (which would panic on OOB)
        if a as usize >= self.classes.len() { return Err(HwineError::InvalidClass(a)); }
        if b as usize >= self.classes.len() { return Err(HwineError::InvalidClass(b)); }
        let a = self.canon_mut(a);
        let b = self.canon_mut(b);
        if self.classes[a as usize].is_none() { return Err(HwineError::DeletedClass(a)); }
        if self.classes[b as usize].is_none() { return Err(HwineError::DeletedClass(b)); }
        if a == b { return Ok(a); }
        Ok(self.union(a, b))
    }

    fn repair_parents(&mut self, cid: u32) {
        let parents: Vec<u32> = self.parents_of[cid as usize].iter().copied().collect();
        let mut to_fix: Vec<(u32, Vec<ENode>)> = Vec::new();

        for p_cid in parents {
            let p_cid = self.canon_mut(p_cid);
            if p_cid == cid {
                continue;
            }
            let p_class = match &self.classes[p_cid as usize] {
                Some(c) => c,
                None => continue,
            };

            let mut needs_repair = false;
            for node in p_class.nodes.iter() {
                let canon: Vec<u32> =
                    node.children.iter().map(|&c| self.canon(c)).collect();
                if canon.as_slice() != node.children.as_ref() {
                    needs_repair = true;
                    break;
                }
            }

            if needs_repair {
                let nodes: Vec<ENode> = p_class
                    .nodes
                    .iter()
                    .map(|n| {
                        let ch: Vec<u32> =
                            n.children.iter().map(|&c| self.canon(c)).collect();
                        ENode::new(n.op, ch, n.dtype)
                    })
                    .collect();
                to_fix.push((p_cid, nodes));
            }
        }

        for (p_cid, nodes) in to_fix {
            if let Some(p) = self.classes[p_cid as usize].as_mut() {
                p.nodes = nodes;
                self.changed.push(p_cid);
            }
        }
    }

    /// Run rules to saturation with configurable pruning
    pub fn saturate(&mut self, max_iter: usize, max_classes: usize) -> usize {
        self.saturate_with_config(max_iter, max_classes, 10, 5, false)
    }

    /// Saturate with pipeline retiming enabled (for streaming/pipelined designs)
    pub fn saturate_retime(&mut self, max_iter: usize, max_classes: usize) -> usize {
        self.saturate_with_config_retime(max_iter, max_classes, 10, 5, false)
    }

    pub fn saturate_with_config(
        &mut self, max_iter: usize, max_classes: usize,
        node_limit: usize, scan_limit: usize, bidir: bool,
    ) -> usize {
        for i in 0..max_iter {
            if self.classes.iter().filter(|c| c.is_some()).count() > max_classes {
                return i;
            }
            let snapshot: Vec<u32> = self.changed.drain(..).collect();
            self.apply_rules_config(&snapshot, node_limit, scan_limit, bidir);

            if self.changed.is_empty() {
                return i + 1;
            }
        }
        max_iter
    }

    fn saturate_with_config_retime(
        &mut self, max_iter: usize, max_classes: usize,
        node_limit: usize, scan_limit: usize, bidir: bool,
    ) -> usize {
        for i in 0..max_iter {
            if self.classes.iter().filter(|c| c.is_some()).count() > max_classes {
                return i;
            }
            let snapshot: Vec<u32> = self.changed.drain(..).collect();
            self.apply_rules_config(&snapshot, node_limit, scan_limit, bidir);
            self.rule_pipeline_retime(&snapshot, node_limit);

            if self.changed.is_empty() {
                return i + 1;
            }
        }
        max_iter
    }

    fn apply_rules_config(&mut self, worklist: &[u32], node_limit: usize, scan_limit: usize, bidir: bool) {
        // Rule gating rationale:
        // - DSP pre-adder and distributive are always enabled: they map algebra to
        //   FPGA primitives without changing cycle-level semantics.
        // - Pipeline retiming (rule_pipeline_retime) is gated behind saturate_retime():
        //   it creates StreamFifo alternatives that trade off delay-cycle latency,
        //   which can produce Pareto-inferior results for combinational-only benchmarks.
        //   Users explicitly opt into retiming via saturate_retime() for pipelined designs.
        let mut to_process: FxHashSet<u32> = FxHashSet::default();
        for &cid in worklist {
            let cid = self.canon(cid);
            to_process.insert(cid);
            for &p in self.parents_of[cid as usize].iter() {
                to_process.insert(self.canon(p));
            }
        }
        let to_process: Vec<u32> = to_process.into_iter().collect();

        self.rule_assoc(&to_process, node_limit, scan_limit, bidir);
        self.rule_mac_decompose(&to_process, node_limit);
        self.rule_mac_fuse(&to_process, node_limit);
        self.rule_add_identity(&to_process);
        self.rule_mul_identity(&to_process);
        self.rule_const_mul_decompose(&to_process);
        self.rule_shift_simplify(&to_process);
        self.rule_acc_flatten(&to_process, node_limit, scan_limit);
        self.rule_softmax_fold(&to_process, node_limit);
        self.rule_distributive(&to_process, node_limit);
        self.rule_dsp_preadd(&to_process, node_limit);
    }

    // ─── Rewrite Rules ─────────────────────────────────

    fn rule_assoc(&mut self, worklist: &[u32], node_limit: usize, scan_limit: usize, bidir: bool) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c,
                None => continue,
            };
            if class.nodes.len() > node_limit { continue; }

            let nodes: Vec<ENode> = class.nodes.iter().take(scan_limit).cloned().collect();
            for node in nodes {
                if !node.op.is_associative() || node.children.len() != 2 { continue; }

                // Side 0: left child is inner OP → OP(OP(a,b), c) → OP(a, OP(b,c))
                if self.try_assoc(cid, &node, 0, node_limit, scan_limit) { continue; }

                // Side 1: right child is inner OP → OP(a, OP(b,c)) → OP(OP(a,b), c)
                if bidir {
                    self.try_assoc(cid, &node, 1, node_limit, scan_limit);
                }
            }
        }
    }

    fn try_assoc(&mut self, cid: u32, node: &ENode, side: usize, node_limit: usize, scan_limit: usize) -> bool {
        let inner_cid = self.canon_mut(node.children[side]);
        let inner_class = match &self.classes[inner_cid as usize] {
            Some(c) => c,
            None => return false,
        };
        if inner_class.nodes.len() > node_limit { return false; }

        let inner_nodes: Vec<ENode> = inner_class.nodes.iter().take(scan_limit).cloned().collect();
        for inner in inner_nodes {
            if inner.op != node.op || inner.children.len() != 2 { continue; }
            // Type compatibility: only reassociate if overflow mode allows it
            if node.dtype.overflow == OverflowMode::Sat && inner.dtype.overflow == OverflowMode::Sat {
                continue; // Saturating arithmetic is NOT associative
            }

            if side == 0 {
                // OP(OP(a,b), c) → OP(a, OP(b,c))
                let a = inner.children[0]; let b = inner.children[1]; let c = node.children[1];
                let bc = self.add(ENode::new(node.op, vec![b, c], node.dtype));
                let new_node = ENode::new(node.op, vec![a, bc], node.dtype);
                let new_cid = self.add(new_node);
                if new_cid != cid { self.union(new_cid, cid); }
            } else {
                // OP(a, OP(b,c)) → OP(OP(a,b), c)
                let a = node.children[0]; let b = inner.children[0]; let c = inner.children[1];
                let ab = self.add(ENode::new(node.op, vec![a, b], node.dtype));
                let new_node = ENode::new(node.op, vec![ab, c], node.dtype);
                let new_cid = self.add(new_node);
                if new_cid != cid { self.union(new_cid, cid); }
            }
            return true;
        }
        false
    }

    fn rule_mac_decompose(&mut self, worklist: &[u32], _node_limit: usize) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c,
                None => continue,
            };
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if !matches!(node.op, AtomOp::Mac | AtomOp::Madd) || node.children.len() < 3 { continue; }
                let x = node.children[0]; let y = node.children[1]; let z = node.children[2];
                let mul = self.add(ENode::new(AtomOp::Mul, vec![x, y], DataType::default()));
                let add = self.add(ENode::new(AtomOp::Add, vec![mul, z], DataType::default()));
                self.union(add, cid);
                break;
            }
        }
    }

    fn rule_mac_fuse(&mut self, worklist: &[u32], _node_limit: usize) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c,
                None => continue,
            };
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::Add || node.children.len() != 2 { continue; }
                let mul_cid = self.canon(node.children[0]);
                let mul_class = match &self.classes[mul_cid as usize] {
                    Some(c) => c,
                    None => continue,
                };
                for mul_node in mul_class.nodes.iter().take(5) {
                    if mul_node.op == AtomOp::Mul && mul_node.children.len() == 2 {
                        let w = mul_node.children[0]; let a = mul_node.children[1]; let acc = node.children[1];
                        let mac = self.add(ENode::new(AtomOp::Mac, vec![w, a, acc], DataType::default()));
                        self.union(mac, cid);
                        break;
                    }
                }
            }
        }
    }

    fn rule_acc_flatten(&mut self, worklist: &[u32], node_limit: usize, scan_limit: usize) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c,
                None => continue,
            };
            if class.nodes.len() > node_limit { continue; }
            let nodes: Vec<ENode> = class.nodes.iter().take(scan_limit).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::AccStep || node.children.len() != 2 { continue; }
                let prev = self.canon_mut(node.children[0]);
                let prev_class = match &self.classes[prev as usize] {
                    Some(c) => c,
                    None => continue,
                };
                if prev_class.nodes.len() > node_limit { continue; }
                for inner in prev_class.nodes.iter().take(scan_limit) {
                    if inner.op != AtomOp::AccStep || inner.children.len() != 2 { continue; }
                    let init = inner.children[0]; let v1 = inner.children[1]; let v2 = node.children[1];
                    let add = self.add(ENode::new(AtomOp::Add, vec![v1, v2], DataType::default()));
                    let new_node = ENode::new(AtomOp::AccStep, vec![init, add], DataType::default());
                    let new_cid = self.add(new_node);
                    if new_cid != cid { self.union(new_cid, cid); }
                    break;
                }
            }
        }
    }

    fn rule_add_identity(&mut self, worklist: &[u32]) {
        let mut merges: Vec<(u32, u32)> = Vec::new();
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            for node in class.nodes.iter().take(8) {
                if node.op != AtomOp::Add || node.children.len() != 2 { continue; }
                for i in 0..2 {
                    let side = self.canon(node.children[i]);
                    if let Some(sc) = &self.classes[side as usize] {
                        if sc.nodes.iter().any(|n| n.op == AtomOp::Zero) {
                            merges.push((self.canon(node.children[1 - i]), cid));
                            break;
                        }
                    }
                }
            }
        }
        for (other, cid) in merges { self.union(other, cid); }
    }

    fn rule_mul_identity(&mut self, worklist: &[u32]) {
        let mut merges: Vec<(u32, u32)> = Vec::new();
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            for node in class.nodes.iter().take(8) {
                if node.op != AtomOp::Mul || node.children.len() != 2 { continue; }
                for i in 0..2 {
                    let side = self.canon(node.children[i]);
                    if let Some(sc) = &self.classes[side as usize] {
                        if sc.nodes.iter().any(|n| n.op == AtomOp::One) {
                            merges.push((self.canon(node.children[1 - i]), cid));
                            break;
                        }
                    }
                }
            }
        }
        for (other, cid) in merges { self.union(other, cid); }
    }

    fn rule_const_mul_decompose(&mut self, worklist: &[u32]) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::Mul || node.children.len() != 2 { continue; }
                for i in 0..2 {
                    let const_cid = self.canon(node.children[i]);
                    let var_cid = self.canon(node.children[1 - i]);
                    let const_class = match &self.classes[const_cid as usize] {
                        Some(c) => c, None => continue,
                    };
                    // Find Const value
                    let mut k: Option<i64> = None;
                    for cn in const_class.nodes.iter().take(5) {
                        if let AtomOp::Const(v) = cn.op {
                            k = Some(v);
                            break;
                        }
                    }
                    let k = match k { Some(v) => v, None => continue };
                    if k.abs() <= 1 { continue; } // skip 0, ±1 (no decomposition needed)

                    // Build shift-add tree for k
                    let tree = self.build_shift_add_tree(var_cid, k);
                    if let Some(tree_cid) = tree {
                        if tree_cid != cid { self.union(tree_cid, cid); }
                    }
                    break; // one decomposition per node
                }
            }
        }
    }

    /// Build a shift-add tree: k * a → sum of (a << e) terms
    fn build_shift_add_tree(&mut self, base: u32, k: i64) -> Option<u32> {
        if k == 0 { return Some(self.add(ENode::leaf(AtomOp::Zero))); }
        if k == 1 { return Some(base); }

        // Pure power-of-2: k == 1 << e
        if k > 0 && (k & (k - 1)) == 0 {
            let shift = k.trailing_zeros();
            if shift > 0 {
                let c = self.add(ENode::leaf(AtomOp::Const(shift as i64)));
                return Some(self.add(ENode::new(AtomOp::Shl, vec![base, c], DataType::default())));
            }
        }

        // General case: k = sum of powers of 2
        let terms = decompose_to_pow2(k);
        if terms.is_empty() || terms.len() > 6 { return None; } // too complex

        let mut acc = self.add(ENode::leaf(AtomOp::Zero));
        for (sign, e) in &terms {
            let ce = self.add(ENode::leaf(AtomOp::Const(*e as i64)));
            let term = self.add(ENode::new(AtomOp::Shl, vec![base, ce], DataType::default()));
            acc = if *sign >= 0 {
                self.add(ENode::new(AtomOp::Add, vec![acc, term], DataType::default()))
            } else {
                self.add(ENode::new(AtomOp::Sub, vec![acc, term], DataType::default()))
            };
        }
        Some(acc)
    }

    fn rule_shift_simplify(&mut self, worklist: &[u32]) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                // Shl(a, Const(0)) → a
                // Shr(a, Const(0)) → a
                // Add(a, a) → Shl(a, 1)  [aggressive constant folding for common subexpr]
                if matches!(node.op, AtomOp::Shl | AtomOp::Shr) && node.children.len() == 2 {
                    let shift_cid = self.canon(node.children[1]);
                    if let Some(sc) = &self.classes[shift_cid as usize] {
                        if sc.nodes.iter().any(|n| n.op == AtomOp::Const(0)) {
                            let base = self.canon(node.children[0]);
                            if base != cid { self.union(base, cid); }
                        }
                    }
                }
            }
        }
    }

    // ─── Multi-Objective Extraction ─────────────────────────────────────

    /// Extract optimal node with full FPGA resource stats.
    /// mode: MinDelay, MinLut{max_delay}, MinDsp{max_delay}, MinFf{max_delay}, Weighted{...}, Pareto
    ///
    /// # Examples
    ///
    /// ```
    /// use hwine_rs::egraph::EGraph;
    /// use hwine_rs::ir::{AtomOp, ENode, DataType};
    /// use hwine_rs::cost::ExtractMode;
    ///
    /// let mut eg = EGraph::new();
    /// let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
    /// let b = eg.add(ENode::leaf_typed(AtomOp::Var(1), DataType::S16));
    /// let add = eg.add(ENode::new(AtomOp::Add, vec![a, b], DataType::S16));
    /// let (node, stats) = eg.extract_optimal(add, ExtractMode::MinDelay);
    /// assert_eq!(node.op, AtomOp::Add);
    /// assert!(stats.delay_ns <= 1.0);
    /// ```
    pub fn extract_optimal(&self, cid: u32, mode: ExtractMode) -> (ENode, FpgaStats) {
        self._extract_dp(cid, &mut FxHashMap::default(), &mut FxHashSet::default(), mode)
    }

    /// Fallible variant: catches panics from corrupted e-graph state.
    pub fn try_extract_optimal(&self, cid: u32, mode: ExtractMode) -> HwineResult<(ENode, FpgaStats)> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.extract_optimal(cid, mode)
        }))
        .map_err(|_| HwineError::ExtractionFailed("extract_optimal panicked".into()))
    }

    /// Pareto-frontier extraction: returns all non-dominated (node, stats) pairs.
    /// Children are evaluated with MinDelay mode for generality.
    pub fn extract_pareto(&self, cid: u32) -> Vec<(ENode, FpgaStats)> {
        self._extract_pareto(cid, &mut FxHashMap::default(), &mut FxHashSet::default(), ExtractMode::MinDelay)
    }

    /// Pareto-frontier extraction with explicit child evaluation mode.
    /// Use this when you want children ranked under the same cost objective (e.g., MinLut).
    pub fn extract_pareto_with_mode(&self, cid: u32, child_mode: ExtractMode) -> Vec<(ENode, FpgaStats)> {
        self._extract_pareto(cid, &mut FxHashMap::default(), &mut FxHashSet::default(), child_mode)
    }

    /// Fallible Pareto extraction.
    pub fn try_extract_pareto(&self, cid: u32) -> HwineResult<Vec<(ENode, FpgaStats)>> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.extract_pareto(cid)
        }))
        .map_err(|_| HwineError::ExtractionFailed("extract_pareto panicked".into()))
    }

    /// Sharing-aware cost: extracts the DP-optimal tree structure, then recomputes
    /// costs with deduplication of shared e-classes. This fixes double-counting when
    /// the same subtree appears in multiple branches (e.g., ac and bd in complex multiply).
    pub fn extract_shared_aware(&self, cid: u32, mode: ExtractMode) -> (ENode, FpgaStats) {
        let (node, _raw_stats) = self.extract_optimal(cid, mode);
        let mut shared = FxHashSet::default();
        let stats = self.compute_deduped_stats(cid, &node, &mut shared, mode);
        (node, stats)
    }

    /// Fallible shared-aware extraction.
    pub fn try_extract_shared_aware(&self, cid: u32, mode: ExtractMode) -> HwineResult<(ENode, FpgaStats)> {
        std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            self.extract_shared_aware(cid, mode)
        }))
        .map_err(|_| HwineError::ExtractionFailed("extract_shared_aware panicked".into()))
    }

    /// Recursively compute resource stats while deduplicating encountered e-classes.
    /// After first encounter, each e-class's own resources are counted; subsequent
    /// encounters only count wiring overhead (marginal cost).
    fn compute_deduped_stats(&self, cid: u32, node: &ENode, shared: &mut FxHashSet<u32>, mode: ExtractMode) -> FpgaStats {
        let canonical = self.canon(cid);
        let already_seen = !shared.insert(canonical);

        if already_seen {
            return FpgaStats::empty();
        }

        let child_stats: Vec<FpgaStats> = node.children.iter()
            .zip(0..)
            .map(|(&ch_cid, _)| {
                let (child_node, _) = self.extract_optimal(ch_cid, mode);
                self.compute_deduped_stats(ch_cid, &child_node, shared, mode)
            })
            .collect();

        FpgaStats::for_node(node.op, &child_stats, &node.dtype)
    }

    /// Core DP extraction with FpgaStats resource accounting
    fn _extract_dp(
        &self, cid: u32,
        memo: &mut FxHashMap<u32, (ENode, FpgaStats)>,
        visiting: &mut FxHashSet<u32>,
        mode: ExtractMode,
    ) -> (ENode, FpgaStats) {
        let cid = self.canon(cid);
        if let Some(result) = memo.get(&cid) {
            return result.clone();
        }
        // Cycle detection: this CID is already being evaluated higher in the call stack.
        // Return infinite cost (not Zero) so the DP avoids cyclic paths.
        // Returning Zero+empty would incorrectly substitute 0 for variables,
        // corrupting the extracted expression.
        if !visiting.insert(cid) {
            return (ENode::leaf(AtomOp::Zero), FpgaStats::infinite());
        }

        let class = match &self.classes[cid as usize] {
            Some(c) => c,
            None => {
                let inf = FpgaStats::infinite();
                memo.insert(cid, (ENode::leaf(AtomOp::Zero), inf.clone()));
                visiting.remove(&cid);
                return (ENode::leaf(AtomOp::Zero), inf);
            }
        };

        let mut best_node = ENode::leaf(AtomOp::Zero);
        let mut best_stats = FpgaStats::infinite();
        let mut best_cost = f64::INFINITY;

        for node in class.nodes.iter() {
            // Skip nodes with self-referencing children (can happen after union merges)
            if node.children.iter().any(|&ch| self.canon(ch) == cid) {
                continue;
            }
            let mut child_stats: Vec<FpgaStats> = Vec::with_capacity(node.children.len());
            let mut has_infinite_child = false;
            for &ch in node.children.iter() {
                let cs = self._extract_dp(ch, memo, visiting, mode).1;
                if cs.delay_ns >= 1e9 { has_infinite_child = true; }
                child_stats.push(cs);
            }
            if has_infinite_child { continue; } // skip nodes with unreachable children
            let stats = FpgaStats::for_node(node.op, &child_stats, &node.dtype);
            let cost = stats.scalar_cost(mode);

            if cost < best_cost {
                best_cost = cost;
                best_stats = stats;
                best_node = node.clone();
            }
        }

        visiting.remove(&cid);
        memo.insert(cid, (best_node.clone(), best_stats.clone()));
        (best_node, best_stats)
    }

    /// Pareto extraction: enumerates all nodes in each class, computes stats with
    /// optimal children, then filters to non-dominated alternatives.
    /// `child_mode` determines how child e-classes are evaluated (MinDelay default,
    /// but can be MinLut/MinDsp/Weighted for domain-specific Pareto frontiers).
    fn _extract_pareto(
        &self, cid: u32,
        memo: &mut FxHashMap<u32, Vec<(ENode, FpgaStats)>>,
        visiting: &mut FxHashSet<u32>,
        child_mode: ExtractMode,
    ) -> Vec<(ENode, FpgaStats)> {
        let cid = self.canon(cid);
        if let Some(cached) = memo.get(&cid) {
            return cached.clone();
        }
        if !visiting.insert(cid) {
            return vec![(ENode::leaf(AtomOp::Zero), FpgaStats::infinite())];
        }

        let class = match &self.classes[cid as usize] {
            Some(c) => c,
            None => {
                let e = vec![(ENode::leaf(AtomOp::Zero), FpgaStats::empty())];
                memo.insert(cid, e.clone());
                visiting.remove(&cid);
                return e;
            }
        };

        let mut candidates = Vec::new();

        // Shared DP memo: avoids recreating per-child FxHashMap (O(n²) → O(n))
        let mut dp_memo: FxHashMap<u32, (ENode, FpgaStats)> = FxHashMap::default();
        let mut dp_visiting: FxHashSet<u32> = FxHashSet::default();

        for node in class.nodes.iter().take(16) {
            let mut child_stats = Vec::new();
            for &ch in node.children.iter() {
                let (_, stats) = self._extract_dp(ch, &mut dp_memo, &mut dp_visiting, child_mode);
                child_stats.push(stats);
            }
            let stats = FpgaStats::for_node(node.op, &child_stats, &node.dtype);
            candidates.push((node.clone(), stats));
        }

        let filtered = FpgaStats::pareto_filter(candidates);
        visiting.remove(&cid);
        memo.insert(cid, filtered.clone());
        filtered
    }

    pub fn extract_shallowest(&self, cid: u32) -> (ENode, usize) {
        self.extract_depth_dp(cid, &mut FxHashMap::default())
    }

    fn extract_depth_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, usize)>) -> (ENode, usize) {
        self._extract_depth_dp(cid, memo, &mut FxHashSet::default())
    }

    fn _extract_depth_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, usize)>, visiting: &mut FxHashSet<u32>) -> (ENode, usize) {
        // Canonicalize, check memo, and detect cycles — same pattern as _extract_dp
        let cid = self.canon(cid);
        if let Some(result) = memo.get(&cid) {
            return result.clone();
        }
        if !visiting.insert(cid) {
            return (ENode::leaf(AtomOp::Zero), usize::MAX); // cycle
        }

        let class = match &self.classes[cid as usize] {
            Some(c) => c,
            None => {
                // Deleted class: return max depth so callers skip it
                memo.insert(cid, (ENode::leaf(AtomOp::Zero), usize::MAX));
                visiting.remove(&cid);
                return (ENode::leaf(AtomOp::Zero), usize::MAX);
            }
        };
        let mut best_node = ENode::leaf(AtomOp::Zero);
        let mut best_depth = usize::MAX;

        for node in class.nodes.iter() {
            let mut max_child_depth: usize = 0;
            let mut cyclic = false;
            for &ch in node.children.iter() {
                let d = self._extract_depth_dp(ch, memo, visiting).1;
                if d == usize::MAX { cyclic = true; break; }
                if d > max_child_depth { max_child_depth = d; }
            }
            if cyclic { continue; }
            let depth = 1 + max_child_depth;
            if depth < best_depth {
                best_depth = depth;
                best_node = node.clone();
            }
        }
        visiting.remove(&cid);
        memo.insert(cid, (best_node.clone(), best_depth));
        (best_node, best_depth)
    }

    fn rule_softmax_fold(&mut self, worklist: &[u32], _node_limit: usize) {
        let one_id = self.add_leaf(AtomOp::One);
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::Softmax || node.children.len() != 1 { continue; }
                let vec_cid = node.children[0];
                let mx = self.add(ENode::new(AtomOp::ReduceMax, vec![vec_cid, vec_cid], DataType::default()));
                let shifted = self.add(ENode::new(AtomOp::Sub, vec![vec_cid, mx], DataType::default()));
                let expd = self.add(ENode::new(AtomOp::Exp, vec![shifted], DataType::default()));
                let sm = self.add(ENode::new(AtomOp::ReduceAdd, vec![expd, expd], DataType::default()));
                let inv = self.add(ENode::new(AtomOp::Div, vec![one_id, sm], DataType::default()));
                let result = self.add(ENode::new(AtomOp::Mul, vec![expd, inv], DataType::default()));
                self.union(result, cid);
                break;
            }
        }
    }

    fn rule_distributive(&mut self, worklist: &[u32], _node_limit: usize) {
        // (a+b)*c → a*c + b*c  (expand: 1 DSP → 2 DSPs, may reduce depth)
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            if class.nodes.len() > 15 { continue; }
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::Mul || node.children.len() != 2 { continue; }
                // MUL(ADD(a,b), c) → ADD(MUL(a,c), MUL(b,c))
                for side in 0..2 {
                    let add_cid = self.canon(node.children[side]);
                    if let Some(add_cls) = &self.classes[add_cid as usize] {
                        for add_n in add_cls.nodes.iter().take(5) {
                            if add_n.op == AtomOp::Add && add_n.children.len() == 2 {
                                let a = add_n.children[0];
                                let b = add_n.children[1];
                                let c = node.children[1 - side];
                                let ac = self.add(ENode::new(AtomOp::Mul, vec![a, c], DataType::default()));
                                let bc = self.add(ENode::new(AtomOp::Mul, vec![b, c], DataType::default()));
                                let add = self.add(ENode::new(AtomOp::Add, vec![ac, bc], DataType::default()));
                                self.union(add, cid);
                                break;
                            }
                        }
                    }
                }
            }
        }
    }

    pub fn n_classes(&self) -> usize {
        self.classes.iter().filter(|c| c.is_some()).count()
    }

    pub fn union_count(&self) -> u64 {
        self.union_count
    }

    pub fn class_nodes(&self, cid: u32) -> Option<&[ENode]> {
        let cid = self.canon(cid);
        self.classes[cid as usize].as_ref().map(|c| c.nodes.as_slice())
    }

    /// DSP48 pre-adder: Mul(Add(a,b), c) → DspPreAdd(a, b, c)
    /// Uses a single DSP48E1 slice with pre-adder, saving LUTs.
    fn rule_dsp_preadd(&mut self, worklist: &[u32], _node_limit: usize) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            if class.nodes.len() > 15 { continue; }
            let nodes: Vec<ENode> = class.nodes.iter().take(8).cloned().collect();
            for node in nodes {
                if node.op != AtomOp::Mul || node.children.len() != 2 { continue; }
                // MUL(ADD(a,b), c) → DSP_PREADD(a, b, c)
                for side in 0..2 {
                    let add_cid = self.canon(node.children[side]);
                    if let Some(add_cls) = &self.classes[add_cid as usize] {
                        for add_n in add_cls.nodes.iter().take(5) {
                            if add_n.op == AtomOp::Add && add_n.children.len() == 2 {
                                let a = add_n.children[0];
                                let b = add_n.children[1];
                                let c = node.children[1 - side];
                                let preadd = self.add(ENode::new(AtomOp::DspPreAdd, vec![a, b, c], node.dtype));
                                self.union(preadd, cid);
                                break;
                            }
                        }
                    }
                }
            }
        }
    }

    /// Pipeline retiming: any arithmetic operation can be optionally registered.
    /// `Op(a, b, ...) ↔ StreamFifo(Op(a, b, ...))`
    /// Creates a pipeline stage option at every operation point.
    /// Multi-objective extraction then selects FIFO placement based on delay vs FF tradeoff.
    ///
    /// The FIFO version is unified with the original op in the same e-class.
    /// This is valid under retiming equivalence: Reg(Op(x)) and Op(x) produce
    /// the same functional result at different cycle latencies. The cost model
    /// distinguishes them via cycle count (FIFO: +1 cycle) and delay (FIFO: 0.3ns
    /// pipeline barrier), enabling Pareto-optimal pipeline depth selection.
    fn rule_pipeline_retime(&mut self, worklist: &[u32], _node_limit: usize) {
        for &cid in worklist {
            let cid = self.canon_mut(cid);
            let class = match &self.classes[cid as usize] {
                Some(c) => c, None => continue,
            };
            if class.nodes.len() > 20 { continue; }
            let nodes: Vec<ENode> = class.nodes.iter().take(5).cloned().collect();
            for node in nodes {
                // Only apply to arithmetic ops that aren't already pipeline ops
                if !node.op.is_arithmetic() { continue; }
                if matches!(node.op, AtomOp::StreamFifo | AtomOp::Pipe) { continue; }
                if node.children.is_empty() { continue; }

                // Create child e-class via hash-cons (reuses existing node)
                // Union: makes StreamFifo(Op) an extraction alternative to Op
                let inner = self.add(node.clone());
                let fifo = self.add(ENode::new(
                    AtomOp::StreamFifo,
                    vec![inner],
                    node.dtype,
                ));
                self.union(fifo, cid);
            }
        }
    }
}

/// Decompose a positive integer into minimal signed powers-of-2 terms
/// using Canonical Signed Digit (CSD) representation.
/// Returns (sign, exponent) pairs. CSD guarantees at most one non-zero
/// among any two consecutive bits, minimizing the number of shift-add terms.
/// Example: 7 → [(1,3), (-1,0)] = 8 - 1 (2 terms, vs 4+2+1 = 3 terms).
pub(crate) fn decompose_to_pow2(k: i64) -> Vec<(i32, u32)> {
    if k == 0 { return vec![]; }
    if k < 0 {
        // Decompose abs(k) and negate all terms
        let pos_terms = decompose_to_pow2(-k);
        return pos_terms.into_iter().map(|(s, e)| (-s, e)).collect();
    }
    if k == 1 { return vec![(1, 0)]; }
    if (k & (k - 1)) == 0 {
        return vec![(1, k.trailing_zeros())]; // single power of 2
    }

    let mut terms = Vec::new();
    let mut bit: u32 = 0;
    let mut remaining = k;

    while remaining > 0 {
        if remaining & 1 != 0 {
            if (remaining & 3) == 3 {
                terms.push((-1, bit));
                remaining = (remaining + 1) >> 1;
            } else {
                terms.push((1, bit));
                remaining >>= 1;
            }
        } else {
            remaining >>= 1;
        }
        bit += 1;
    }
    // Sort by exponent ascending for stable add-tree construction
    terms.sort_by_key(|(_, e)| *e);
    terms
}
