//! Checked fixed-width integer RTL. See docs/RELIABILITY.md for the contract.
use std::collections::{BTreeMap, HashMap, HashSet};
use std::rc::Rc;

use crate::cost::{ExtractMode, FpgaStats};
use crate::egraph::EGraph;
use crate::error::{HwineError, HwineResult};
use crate::extract::Plan;
use crate::ir::{AtomOp, DataType, ENode, OverflowMode};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Pipeline {
    None,
    /// One register at the output (replaces the old unbalanced coarse helper).
    Output,
    /// Register every arithmetic operation and balance all operand branches.
    EveryOp,
    /// Cut at every N operation-depth levels and register the final partial
    /// stage. N must be positive. Counts IR operations, not physical delay;
    /// constants/variables have depth zero. Branches are cycle-aligned.
    EveryN(usize),
}

#[derive(Debug, Clone)]
pub struct RtlArtifact {
    pub verilog: String,
    /// Number L of register stages. Inputs before edge n appear after edge
    /// n+L-1 (L=0 is combinational). Valid after L non-reset edges of fill.
    pub latency: usize,
    /// Abstract ranking estimates; not synthesis measurements.
    pub estimated: FpgaStats,
}

fn supported(op: AtomOp) -> bool {
    matches!(
        op,
        AtomOp::Var(_)
            | AtomOp::Const(_)
            | AtomOp::Zero
            | AtomOp::One
            | AtomOp::Add
            | AtomOp::Sub
            | AtomOp::Mul
            | AtomOp::Mac
            | AtomOp::Madd
            | AtomOp::DspMul
            | AtomOp::DspMac
            | AtomOp::DspPreAdd
            | AtomOp::Shl
            | AtomOp::Shr
            | AtomOp::ReduceAdd
            | AtomOp::ReduceMin
            | AtomOp::ReduceMax
            | AtomOp::Pipe
    )
}

/// Check every reachable alternative, so a cheap alternative cannot hide an
/// unsupported atom, malformed arity, or mixed-width expression in its class.
fn validate_graph(eg: &EGraph, root: u32) -> HwineResult<DataType> {
    let mut seen = HashSet::new();
    let mut todo = vec![root];
    let mut var_types = HashMap::new();
    while let Some(cid) = todo.pop() {
        let nodes = eg.class_nodes(cid).ok_or(HwineError::InvalidClass(cid))?;
        if !seen.insert(eg.canon(cid)) {
            continue;
        }
        let dtype = nodes.first().ok_or(HwineError::DeletedClass(cid))?.dtype;
        for node in nodes {
            if !supported(node.op) {
                return Err(HwineError::UnsupportedRtlOp(node.op));
            }
            if node.dtype != dtype {
                return Err(HwineError::InvalidInput("mixed types in e-class"));
            }
            if !(1..=64).contains(&dtype.width) || dtype.overflow != OverflowMode::Wrap {
                return Err(HwineError::InvalidInput(
                    "RTL requires 1..=64 bit wrapping integers",
                ));
            }
            if node.children.len() != node.op.arity() {
                return Err(HwineError::InvalidInput("operation arity mismatch"));
            }
            if let AtomOp::Var(id) = node.op
                && var_types.insert(id, dtype).is_some_and(|t| t != dtype)
            {
                return Err(HwineError::InvalidInput(
                    "one variable has conflicting types",
                ));
            }
            for (i, &c) in node.children.iter().enumerate() {
                let cn = eg.class_nodes(c).ok_or(HwineError::InvalidClass(c))?;
                for n in cn {
                    let shift_count = matches!(node.op, AtomOp::Shl | AtomOp::Shr) && i == 1;
                    if shift_count {
                        if n.dtype.signed {
                            return Err(HwineError::InvalidInput("shift count must be unsigned"));
                        }
                    } else if n.dtype != dtype {
                        return Err(HwineError::InvalidInput(
                            "operands and result must have the same integer type",
                        ));
                    }
                }
                todo.push(c);
            }
        }
    }
    Ok(eg.class_nodes(root).unwrap()[0].dtype)
}

fn identifier(s: &str) -> bool {
    // Verilog/SystemVerilog keywords are not ordinary identifiers.
    let keywords = "accept_on alias always always_comb always_ff always_latch and assert assign assume automatic before begin bind bins binsof bit break buf bufif0 bufif1 byte case casex casez cell chandle checker class clocking cmos config const constraint context continue cover covergroup coverpoint cross deassign default defparam design disable dist do edge else end endcase endchecker endclass endclocking endconfig endfunction endgenerate endgroup endinterface endmodule endpackage endprimitive endprogram endproperty endspecify endsequence endtable endtask enum event eventually expect export extends extern final first_match for force foreach forever fork forkjoin function generate genvar global highz0 highz1 if iff ifnone ignore_bins illegal_bins implements implies import incdir include initial inout input inside instance int integer interconnect interface intersect join join_any join_none large let liblist library local localparam logic longint macromodule matches medium modport module nand negedge nettype new nexttime nmos nor noshowcancelled not notif0 notif1 null or output package packed parameter pmos posedge primitive priority program property protected pull0 pull1 pulldown pullup pulsestyle_onevent pulsestyle_ondetect pure rand randc randcase randsequence rcmos real realtime ref reg reject_on release repeat restrict return rnmos rpmos rtran rtranif0 rtranif1 s_always s_eventually s_nexttime s_until s_until_with scalared sequence shortint shortreal showcancelled signed small soft solve specify specparam static string strong strong0 strong1 struct super supply0 supply1 sync_accept_on sync_reject_on table tagged task this throughout time timeprecision timeunit tran tranif0 tranif1 tri tri0 tri1 triand trior trireg type typedef union unique unique0 unsigned until until_with untyped use uwire var vectored virtual void wait wait_order wand weak weak0 weak1 while wildcard wire with within wone wor xnor xor";
    let mut chars = s.chars();
    matches!(chars.next(), Some(c) if c.is_ascii_alphabetic() || c == '_')
        && chars.all(|c| c.is_ascii_alphanumeric() || c == '_')
        && !keywords.split_whitespace().any(|k| k == s)
}

fn make_plan(op: AtomOp, dtype: DataType, children: Vec<Rc<Plan>>) -> Rc<Plan> {
    let stats = FpgaStats::for_node(
        op,
        &children.iter().map(|c| c.stats.clone()).collect::<Vec<_>>(),
        &dtype,
    );
    // Child IDs are no longer used after extraction; the actual children live here.
    Rc::new(Plan {
        node: ENode::new(op, vec![], dtype),
        children,
        stats,
    })
}

fn register(p: Rc<Plan>) -> Rc<Plan> {
    make_plan(AtomOp::Pipe, p.node.dtype, vec![p])
}

fn schedule(
    p: &Rc<Plan>,
    interval: usize,
    memo: &mut HashMap<usize, (Rc<Plan>, usize)>,
) -> (Rc<Plan>, usize) {
    let key = Rc::as_ptr(p) as usize;
    if let Some(v) = memo.get(&key) {
        return v.clone();
    }
    let out = if p.children.is_empty() {
        (p.clone(), 0)
    } else {
        let scheduled: Vec<_> = p
            .children
            .iter()
            .map(|c| schedule(c, interval, memo))
            .collect();
        let depth = 1 + scheduled.iter().map(|(_, d)| *d).max().unwrap_or(0);
        let level = (depth - 1) / interval;
        let mut children: Vec<_> = scheduled.into_iter().map(|(c, _)| c).collect();
        for c in &mut children {
            while c.stats.cycles < level {
                *c = register(c.clone());
            }
        }
        let mut node = make_plan(p.node.op, p.node.dtype, children);
        if depth % interval == 0 {
            node = register(node);
        }
        (node, depth)
    };
    memo.insert(key, out.clone());
    out
}

fn validate_plan(p: &Rc<Plan>, seen: &mut HashSet<usize>) -> HwineResult<()> {
    if !seen.insert(Rc::as_ptr(p) as usize) {
        return Ok(());
    }
    if p.children
        .windows(2)
        .any(|pair| pair[0].stats.cycles != pair[1].stats.cycles)
    {
        return Err(HwineError::InvalidInput(
            "operand cycle mismatch; align all branches with Pipe",
        ));
    }
    for c in &p.children {
        validate_plan(c, seen)?;
    }
    Ok(())
}

fn decl(dtype: DataType) -> String {
    format!(
        "logic {}[{}:0]",
        if dtype.signed { "signed " } else { "" },
        dtype.width - 1
    )
}

struct Emitter {
    wires: HashMap<usize, String>,
    ports: BTreeMap<usize, (String, DataType)>,
    names: HashMap<usize, String>,
    lines: Vec<String>,
    has_clk: bool,
}

impl Emitter {
    fn emit(&mut self, p: &Rc<Plan>) -> HwineResult<String> {
        let key = Rc::as_ptr(p) as usize;
        if let Some(w) = self.wires.get(&key) {
            return Ok(w.clone());
        }
        let children: Vec<_> = p
            .children
            .iter()
            .map(|c| self.emit(c))
            .collect::<HwineResult<_>>()?;
        let w = format!("hwine_n{}", self.wires.len());
        self.wires.insert(key, w.clone());
        self.lines.push(format!("  {} {w};", decl(p.node.dtype)));
        let expr = match p.node.op {
            AtomOp::Var(id) => {
                let name = self.names.get(&id).cloned().unwrap_or_else(|| {
                    if id % 2 == 0 {
                        format!("a{}", id / 2)
                    } else {
                        format!("w{}", id / 2)
                    }
                });
                if !identifier(&name)
                    || name.starts_with("hwine_")
                    || ["result", "clk", "rst_n"].contains(&name.as_str())
                {
                    return Err(HwineError::InvalidInput("invalid or reserved input name"));
                }
                if self
                    .ports
                    .iter()
                    .any(|(&other, (n, _))| other != id && n == &name)
                {
                    return Err(HwineError::PortConflict {
                        name,
                        declared_as: format!("Var({id})"),
                        conflicting_as: "another input".into(),
                    });
                }
                self.ports.insert(id, (name.clone(), p.node.dtype));
                name
            }
            AtomOp::Const(v) => {
                let mask = u64::MAX >> (64 - p.node.dtype.width);
                format!("{}'h{:x}", p.node.dtype.width, (v as u64) & mask)
            }
            AtomOp::Zero => "'0".into(),
            AtomOp::One => format!("{}'d1", p.node.dtype.width),
            AtomOp::Add | AtomOp::ReduceAdd => format!("{} + {}", children[0], children[1]),
            AtomOp::Sub => format!("{} - {}", children[0], children[1]),
            AtomOp::Mul | AtomOp::DspMul => format!("{} * {}", children[0], children[1]),
            AtomOp::Mac | AtomOp::Madd | AtomOp::DspMac => {
                format!("({} * {}) + {}", children[0], children[1], children[2])
            }
            AtomOp::DspPreAdd => format!("({} + {}) * {}", children[0], children[1], children[2]),
            AtomOp::Shl => format!("{} << {}", children[0], children[1]),
            AtomOp::Shr => format!(
                "{} {} {}",
                children[0],
                if p.node.dtype.signed { ">>>" } else { ">>" },
                children[1]
            ),
            AtomOp::ReduceMin => format!("({0} < {1}) ? {0} : {1}", children[0], children[1]),
            AtomOp::ReduceMax => format!("({0} > {1}) ? {0} : {1}", children[0], children[1]),
            AtomOp::Pipe => {
                self.has_clk = true;
                self.lines.push(format!("  always_ff @(posedge clk) begin\n    if (!rst_n) {w} <= '0;\n    else {w} <= {};\n  end", children[0]));
                return Ok(w);
            }
            op => return Err(HwineError::UnsupportedRtlOp(op)),
        };
        self.lines.push(format!("  assign {w} = {expr};"));
        Ok(w)
    }
}

fn generate_named(
    eg: &EGraph,
    root: u32,
    module: &str,
    width: usize,
    mode: ExtractMode,
    pipeline: Pipeline,
    names: HashMap<usize, String>,
) -> HwineResult<RtlArtifact> {
    if !identifier(module) {
        return Err(HwineError::InvalidInput("invalid module identifier"));
    }
    let dtype = validate_graph(eg, root)?;
    if width != dtype.width as usize {
        return Err(HwineError::InvalidInput(
            "module width must equal root width",
        ));
    }
    let mut plan = eg.extract_plan(root, mode)?;
    validate_plan(&plan, &mut HashSet::new())?;
    if pipeline != Pipeline::None && plan.stats.cycles != 0 {
        return Err(HwineError::InvalidInput(
            "automatic pipelining requires a combinational input plan",
        ));
    }
    plan = match pipeline {
        Pipeline::None => plan,
        Pipeline::Output => register(plan),
        Pipeline::EveryOp | Pipeline::EveryN(_) => {
            let interval = match pipeline {
                Pipeline::EveryN(0) => {
                    return Err(HwineError::InvalidInput(
                        "pipeline interval must be positive",
                    ));
                }
                Pipeline::EveryN(n) => n,
                _ => 1,
            };
            let (mut scheduled, depth) = schedule(&plan, interval, &mut HashMap::new());
            if depth % interval != 0 {
                scheduled = register(scheduled);
            }
            scheduled
        }
    };
    validate_plan(&plan, &mut HashSet::new())?;
    let mut emitter = Emitter {
        wires: HashMap::new(),
        ports: BTreeMap::new(),
        names,
        lines: vec![],
        has_clk: false,
    };
    let result = emitter.emit(&plan)?;
    let mut ports = vec![];
    if emitter.has_clk {
        ports.extend([
            "  input  logic clk".to_string(),
            "  input  logic rst_n".to_string(),
        ]);
    }
    for (name, t) in emitter.ports.values() {
        ports.push(format!("  input {} {name}", decl(*t)));
    }
    ports.push(format!("  output {} result", decl(dtype)));
    let verilog = format!(
        "// hwine fixed-width wrapping integer RTL; latency = {} cycles.\n// Synchronous active-low reset; accept a new input tuple every cycle.\n`default_nettype none\nmodule {module}(\n{}\n);\n{}\n  assign result = {result};\nendmodule\n`default_nettype wire\n",
        plan.stats.cycles,
        ports.join(",\n"),
        emitter.lines.join("\n")
    );
    Ok(RtlArtifact {
        verilog,
        latency: plan.stats.cycles,
        estimated: plan.stats.clone(),
    })
}

/// Generate a checked implementation and its explicit latency contract.
pub fn try_generate(
    eg: &EGraph,
    root: u32,
    module: &str,
    width: usize,
    mode: ExtractMode,
    pipeline: Pipeline,
) -> HwineResult<RtlArtifact> {
    generate_named(eg, root, module, width, mode, pipeline, HashMap::new())
}

/// Fallible default generation. Errors retain their specific variant.
pub fn try_generate_rtl(eg: &EGraph, root: u32, module: &str, width: usize) -> HwineResult<String> {
    Ok(try_generate(
        eg,
        root,
        module,
        width,
        ExtractMode::MinDelay,
        Pipeline::None,
    )?
    .verilog)
}

/// Convenience wrapper, panics on invalid or unsupported input.
/// ```
/// use hwine_rs::{egraph::EGraph, ir::{AtomOp, ENode, DataType}, rtl::generate_rtl};
/// let mut eg = EGraph::new();
/// let a = eg.add(ENode::leaf_typed(AtomOp::Var(0), DataType::S16));
/// assert!(generate_rtl(&eg, a, "identity", 16).contains("module identity"));
/// ```
pub fn generate_rtl(eg: &EGraph, root: u32, module: &str, width: usize) -> String {
    try_generate_rtl(eg, root, module, width).expect("RTL generation failed")
}

/// Output-register convenience wrapper. Use try_generate to obtain latency.
pub fn generate_pipelined_rtl(eg: &EGraph, root: u32, module: &str, width: usize) -> String {
    try_generate(
        eg,
        root,
        module,
        width,
        ExtractMode::MinDelay,
        Pipeline::Output,
    )
    .expect("RTL generation failed")
    .verilog
}

/// Register each operation and align branches, including shared subexpressions.
pub fn generate_fine_pipelined_rtl(eg: &EGraph, root: u32, module: &str, width: usize) -> String {
    try_generate(
        eg,
        root,
        module,
        width,
        ExtractMode::MinDelay,
        Pipeline::EveryOp,
    )
    .expect("RTL generation failed")
    .verilog
}

/// Legacy naming adapter. A single complete root is emitted atomically.
pub struct RtlGen {
    module: String,
    width: usize,
    names: HashMap<u32, String>,
    output: Option<String>,
}

impl RtlGen {
    pub fn new(module: &str, width: usize) -> Self {
        Self {
            module: module.into(),
            width,
            names: HashMap::new(),
            output: None,
        }
    }
    pub fn set_name(&mut self, cid: u32, name: &str) {
        self.names.insert(cid, name.into());
    }
    pub fn emit_node(
        &mut self,
        eg: &EGraph,
        cid: u32,
        is_root: bool,
        _visited: &mut HashMap<u32, bool>,
    ) -> HwineResult<String> {
        self.output = None;
        if !is_root {
            return Err(HwineError::InvalidInput(
                "emit_node requires a complete root",
            ));
        }
        let mut names = HashMap::new();
        for (&id, name) in &self.names {
            let nodes = eg.class_nodes(id).ok_or(HwineError::InvalidClass(id))?;
            let var = nodes
                .iter()
                .find_map(|n| {
                    if let AtomOp::Var(v) = n.op {
                        Some(v)
                    } else {
                        None
                    }
                })
                .ok_or(HwineError::InvalidInput(
                    "set_name requires a variable class",
                ))?;
            if names
                .insert(var, name.clone())
                .is_some_and(|old| old != *name)
            {
                return Err(HwineError::InvalidInput(
                    "conflicting names for one variable",
                ));
            }
        }
        self.output = Some(
            generate_named(
                eg,
                cid,
                &self.module,
                self.width,
                ExtractMode::MinDelay,
                Pipeline::None,
                names,
            )?
            .verilog,
        );
        Ok("result".into())
    }
    pub fn generate(&self) -> String {
        self.output
            .clone()
            .expect("emit a valid root before generate")
    }
}
