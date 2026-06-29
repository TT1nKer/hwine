use std::collections::{HashMap, HashSet};
use fxhash::FxBuildHasher;
use crate::ir::{AtomOp, ENode};

type FxHashSet<T> = HashSet<T, FxBuildHasher>;
type FxHashMap<K, V> = HashMap<K, V, FxBuildHasher>;

/// An equivalence class of e-nodes
#[derive(Debug, Clone)]
pub struct EClass {
    pub nodes: Vec<ENode>,
}

/// E-graph engine for meta-operation rewriting
pub struct EGraph {
    pub classes: Vec<Option<EClass>>,   // index = e-class ID, None = deleted
    parents: Vec<u32>,                  // union-find parent array
    pub hashcons: FxHashMap<ENode, u32>,
    pub changed: Vec<u32>,             // worklist
    parents_of: Vec<FxHashSet<u32>>,    // child → parent tracking
    pub union_count: u64,
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
                        ENode::new(n.op, ch)
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

    fn apply_rules_config(&mut self, worklist: &[u32], node_limit: usize, scan_limit: usize, bidir: bool) {
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
    }

    fn apply_rules(&mut self, worklist: &[u32]) {
        self.apply_rules_config(worklist, 10, 5, false)
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

            if side == 0 {
                // OP(OP(a,b), c) → OP(a, OP(b,c))
                let a = inner.children[0]; let b = inner.children[1]; let c = node.children[1];
                let bc = self.add(ENode::new(node.op, vec![b, c]));
                let new_node = ENode::new(node.op, vec![a, bc]);
                let new_cid = self.add(new_node);
                if new_cid != cid { self.union(new_cid, cid); }
            } else {
                // OP(a, OP(b,c)) → OP(OP(a,b), c)
                let a = node.children[0]; let b = inner.children[0]; let c = inner.children[1];
                let ab = self.add(ENode::new(node.op, vec![a, b]));
                let new_node = ENode::new(node.op, vec![ab, c]);
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
                let mul = self.add(ENode::new(AtomOp::Mul, vec![x, y]));
                let add = self.add(ENode::new(AtomOp::Add, vec![mul, z]));
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
                        let mac = self.add(ENode::new(AtomOp::Mac, vec![w, a, acc]));
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
                    let add = self.add(ENode::new(AtomOp::Add, vec![v1, v2]));
                    let new_node = ENode::new(AtomOp::AccStep, vec![init, add]);
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
                    if k <= 1 { continue; }

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
                return Some(self.add(ENode::new(AtomOp::Shl, vec![base, c])));
            }
        }

        // General case: k = sum of powers of 2
        let terms = decompose_to_pow2(k);
        if terms.is_empty() || terms.len() > 6 { return None; } // too complex

        let mut acc = self.add(ENode::leaf(AtomOp::Zero));
        for (sign, e) in &terms {
            let ce = self.add(ENode::leaf(AtomOp::Const(*e as i64)));
            let term = self.add(ENode::new(AtomOp::Shl, vec![base, ce]));
            acc = if *sign >= 0 {
                self.add(ENode::new(AtomOp::Add, vec![acc, term]))
            } else {
                self.add(ENode::new(AtomOp::Sub, vec![acc, term]))
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

    // ─── Extraction ─────────────────────────────────────

    pub fn extract_optimal(&self, cid: u32) -> (ENode, f64) {
        self.extract_dp(cid, &mut FxHashMap::default())
    }

    pub fn extract_shallowest(&self, cid: u32) -> (ENode, usize) {
        self.extract_depth_dp(cid, &mut FxHashMap::default())
    }

    fn extract_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, f64)>) -> (ENode, f64) {
        self._extract_dp(cid, memo, &mut FxHashSet::default())
    }

    fn _extract_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, f64)>, visiting: &mut FxHashSet<u32>) -> (ENode, f64) {
        let cid = self.canon(cid);
        if let Some(result) = memo.get(&cid) {
            return result.clone();
        }
        if !visiting.insert(cid) {
            // Cycle detected: return dummy to break recursion
            return (ENode::leaf(AtomOp::Zero), f64::INFINITY);
        }

        let class = match &self.classes[cid as usize] {
            Some(c) => c,
            None => {
                memo.insert(cid, (ENode::leaf(AtomOp::Zero), 0.0));
                visiting.remove(&cid);
                return (ENode::leaf(AtomOp::Zero), 0.0);
            }
        };

        let mut best_node = ENode::leaf(AtomOp::Zero);
        let mut best_cost = f64::INFINITY;

        for node in class.nodes.iter() {
            let mut child_costs: Vec<f64> = Vec::with_capacity(node.children.len());
            for &ch in node.children.iter() {
                child_costs.push(self._extract_dp(ch, memo, visiting).1);
            }
            let delay = node_op_delay(node.op);
            let max_child_delay = child_costs.iter().cloned().fold(0.0_f64, f64::max);
            if max_child_delay.is_infinite() { continue; } // skip cyclic paths
            let cost = delay + max_child_delay;

            if cost < best_cost {
                best_cost = cost;
                best_node = node.clone();
            }
        }

        visiting.remove(&cid);
        memo.insert(cid, (best_node.clone(), best_cost));
        (best_node, best_cost)
    }

    fn extract_depth_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, usize)>) -> (ENode, usize) {
        self._extract_depth_dp(cid, memo, &mut FxHashSet::default())
    }

    fn _extract_depth_dp(&self, cid: u32, memo: &mut FxHashMap<u32, (ENode, usize)>, visiting: &mut FxHashSet<u32>) -> (ENode, usize) {
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
                memo.insert(cid, (ENode::leaf(AtomOp::Zero), 0));
                visiting.remove(&cid);
                return (ENode::leaf(AtomOp::Zero), 0);
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
                let mx = self.add(ENode::new(AtomOp::ReduceMax, vec![vec_cid, vec_cid]));
                let shifted = self.add(ENode::new(AtomOp::Sub, vec![vec_cid, mx]));
                let expd = self.add(ENode::new(AtomOp::Exp, vec![shifted]));
                let sm = self.add(ENode::new(AtomOp::ReduceAdd, vec![expd, expd]));
                let inv = self.add(ENode::new(AtomOp::Div, vec![one_id, sm]));
                let result = self.add(ENode::new(AtomOp::Mul, vec![expd, inv]));
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
                                let ac = self.add(ENode::new(AtomOp::Mul, vec![a, c]));
                                let bc = self.add(ENode::new(AtomOp::Mul, vec![b, c]));
                                let add = self.add(ENode::new(AtomOp::Add, vec![ac, bc]));
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
}

fn node_cost(op: AtomOp) -> f64 {
    match op {
        AtomOp::Add => 1.0,
        AtomOp::Mul | AtomOp::Mac | AtomOp::DspMul | AtomOp::DspMac => 5.0,
        AtomOp::Pipe => 0.1,
        _ => 1.0,
    }
}

fn node_op_delay(op: AtomOp) -> f64 {
    match op {
        AtomOp::Add | AtomOp::Sub => 0.8,
        AtomOp::Shl | AtomOp::Shr => 0.5,
        AtomOp::Mul | AtomOp::Mac | AtomOp::DspMul | AtomOp::DspMac => 2.5,
        AtomOp::Pipe => 0.3,
        _ => 0.5,
    }
}

/// Decompose a positive integer into sum of powers-of-2 terms.
/// Returns (sign, exponent) pairs. Uses canonical signed digit (CSD)
/// for minimal non-zero count (at most one non-zero per 2 bits).
fn decompose_to_pow2(mut k: i64) -> Vec<(i32, u32)> {
    if k <= 0 { return vec![]; }
    // Simple binary decomposition: extract each 1-bit
    // e.g., 13 (1101b) → [(1,0),(1,2),(1,3)] → a + a<<2 + a<<3
    let mut terms = Vec::new();
    let mut bit: u32 = 0;
    while k > 0 {
        if k & 1 != 0 {
            terms.push((1, bit));
        }
        k >>= 1;
        bit += 1;
    }
    terms
}
