// C FFI for hwine-rs — callable from C/C++ (Yosys pass)
use std::ffi::CString;
use std::os::raw::c_char;

use crate::cost::ExtractMode;
use crate::egraph::EGraph;
use crate::ir::DataType;
use crate::ir::{AtomOp, ENode};

/// Result of a hwine optimization pass
#[repr(C)]
pub struct HwineResult {
    pub nodes_before: u32,
    pub nodes_after: u32,
    pub depth_before: u32,
    pub depth_after: u32,
    pub time_ms: f64,
    pub speedup: f64,
}

/// Optimize an ADD chain of `n_inputs` elements.
/// Returns optimization result via the provided pointer.
/// # Safety
/// `result` must be a valid pointer to HwineResult.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn hwine_optimize_add_chain(
    n_inputs: u32,
    bidir: bool,
    loose: bool,
    result: *mut HwineResult,
) -> i32 {
    // Validate inputs
    if result.is_null() {
        return -1;
    }
    if n_inputs == 0 {
        return -2;
    }
    let n = n_inputs as usize;
    let mut eg = EGraph::new();

    let mut vars = Vec::with_capacity(n);
    for i in 0..n {
        vars.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }
    let mut chain = vars[0];
    for &value in vars.iter().skip(1) {
        chain = eg.add(ENode::new(
            AtomOp::Add,
            vec![chain, value],
            DataType::default(),
        ));
    }

    let nl = if loose { 30 } else { 10 };
    let sl = if loose { 20 } else { 8 };

    let t0 = std::time::Instant::now();
    let _iters = eg.saturate_with_config(50, 30000, nl, sl, bidir);
    let dt = t0.elapsed();

    let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    let tree_depth = depth_of(&best, &eg);
    let serial_depth = n - 1; // chain depth

    unsafe {
        (*result).nodes_before = n as u32;
        (*result).nodes_after = n as u32;
        (*result).depth_before = serial_depth as u32;
        (*result).depth_after = tree_depth as u32;
        (*result).time_ms = dt.as_secs_f64() * 1000.0;
        (*result).speedup = serial_depth as f64 / tree_depth.max(1) as f64;
    }
    0 // success
}

/// Optimize a Yosys-style netlist described as an edge list.
/// `edges`: array of [parent, child] pairs, length `n_edges`
/// Returns 0 on success, -1 on error.
/// # Safety
/// `edges` must reference `n_edges` readable pairs; `result` must be writable,
/// aligned storage for one HwineResult. These regions must not overlap.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn hwine_optimize_graph(
    edges: *const [u32; 2],
    n_edges: u32,
    n_nodes: u32,
    result: *mut HwineResult,
) -> i32 {
    // Validate inputs
    if result.is_null() || edges.is_null() {
        return -1;
    }
    if n_edges == 0 || n_nodes == 0 {
        return -2;
    }
    let n_edges = n_edges as usize;
    let n_nodes = n_nodes as usize;

    // Build e-graph from edge list
    let mut eg = EGraph::new();
    let mut node_to_cid: Vec<u32> = vec![0; n_nodes];

    for (i, cid) in node_to_cid.iter_mut().enumerate() {
        *cid = eg.add(ENode::leaf(AtomOp::Var(i)));
    }

    // Parse edges: [parent, child] means parent = ADD(child_a, child_b)
    let mut root = 0u32;
    unsafe {
        for i in 0..n_edges {
            let parent = (*edges.add(i))[0];
            let child = (*edges.add(i))[1];
            let p = parent as usize;
            let c = child as usize;
            if p >= n_nodes || c >= n_nodes {
                return -3; // edge index out of bounds
            }
            // Create ADD(parent, child)
            node_to_cid[p] = eg.add(ENode::new(
                AtomOp::Add,
                vec![node_to_cid[p], node_to_cid[c]],
                DataType::default(),
            ));
            root = node_to_cid[p];
        }
    }

    let t0 = std::time::Instant::now();
    let _iters = eg.saturate_with_config(50, 30000, 10, 8, false);
    let dt = t0.elapsed();

    let (best, _) = eg.extract_optimal(root, ExtractMode::MinDelay);
    let tree_depth = depth_of(&best, &eg);

    unsafe {
        (*result).nodes_before = n_nodes as u32;
        (*result).nodes_after = n_nodes as u32;
        (*result).depth_before = n_edges as u32;
        (*result).depth_after = tree_depth as u32;
        (*result).time_ms = dt.as_secs_f64() * 1000.0;
        (*result).speedup = n_edges as f64 / tree_depth.max(1) as f64;
    }
    0
}

fn depth_of(node: &ENode, eg: &EGraph) -> usize {
    if node.children.is_empty() {
        return 0;
    }
    1 + node
        .children
        .iter()
        .map(|&c| depth_of(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
        .max()
        .unwrap_or(0)
}

/// Get version string. Caller must free with hwine_free_string.
/// # Safety
/// The returned pointer must be freed once, using hwine_free_string only.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn hwine_version() -> *mut c_char {
    let s = CString::new("hwine-rs 0.1.0").unwrap();
    s.into_raw()
}

/// Free a string returned by hwine_version.
/// # Safety
/// `s` must be null or an unmodified pointer from hwine_version that has not
/// already been freed. No other code may use it after this call.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn hwine_free_string(s: *mut c_char) {
    unsafe {
        if !s.is_null() {
            drop(CString::from_raw(s));
        }
    }
}
