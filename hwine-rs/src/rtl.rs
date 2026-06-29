use std::collections::HashMap;
use crate::egraph::EGraph;
use crate::ir::DataType;
use crate::ir::{AtomOp, ENode};
use crate::cost::ExtractMode;

/// SystemVerilog RTL generator from e-graph extraction
pub struct RtlGen {
    module_name: String,
    data_width: usize,
    wire_counter: u32,
    wires: HashMap<u32, String>,
    ports: Vec<(String, String, usize)>,
    assign_lines: Vec<String>,
    ff_lines: Vec<String>,
    has_clk: bool,
    root_wire: String,
    name_map: HashMap<u32, String>, // e-class ID → port name hint
}

impl RtlGen {
    pub fn new(module_name: &str, data_width: usize) -> Self {
        Self {
            module_name: module_name.to_string(),
            data_width,
            wire_counter: 0,
            wires: HashMap::new(),
            ports: Vec::new(),
            assign_lines: Vec::new(),
            ff_lines: Vec::new(),
            has_clk: false,
            root_wire: String::new(),
            name_map: HashMap::new(),
        }
    }

    /// Register a name for a specific Var node's e-class
    pub fn set_name(&mut self, cid: u32, name: &str) {
        self.name_map.insert(cid, name.to_string());
    }

    fn fresh_wire(&mut self, prefix: &str) -> String {
        self.wire_counter += 1;
        format!("{prefix}_{}", self.wire_counter)
    }

    fn wire_for_cid(&mut self, cid: u32, prefix: &str) -> String {
        if let Some(w) = self.wires.get(&cid) {
            return w.clone();
        }
        let w = self.fresh_wire(prefix);
        self.wires.insert(cid, w.clone());
        w
    }

    pub fn emit_node(&mut self, eg: &EGraph, cid: u32, is_root: bool, visited: &mut HashMap<u32, bool>) -> String {
        let cid = eg.canon(cid);
        if let Some(w) = self.wires.get(&cid) {
            return w.clone();
        }
        if visited.contains_key(&cid) {
            let w = self.fresh_wire("cycle");
            self.wires.insert(cid, w.clone());
            self.assign_lines.push(format!("  assign {w} = 0;  // cycle break"));
            return w;
        }
        visited.insert(cid, true);

        let (best_node, _) = eg.extract_optimal(cid, ExtractMode::MinDelay);
        let result = self.emit_enode(eg, &best_node, cid, visited);
        if is_root {
            self.root_wire = result.clone();
        }
        result
    }

    fn emit_enode(
        &mut self,
        eg: &EGraph,
        node: &ENode,
        cid: u32,
        visited: &mut HashMap<u32, bool>,
    ) -> String {
        let w = self.wire_for_cid(cid, "node");

        fn child_wire(
            g: &mut RtlGen,
            eg: &EGraph,
            node: &ENode,
            idx: usize,
            visited: &mut HashMap<u32, bool>,
        ) -> String {
            if idx < node.children.len() {
                g.emit_node(eg, node.children[idx], false, visited)
            } else {
                "0".to_string()
            }
        }

        let dw = node.dtype.width as usize;
        let _signed = if node.dtype.signed { "signed " } else { "" };
        match node.op {
            AtomOp::Var(idx) => {
                let name = self.name_map.get(&cid)
                    .cloned()
                    .unwrap_or_else(|| {
                        // Auto-name: even idx → aX, odd idx → wX
                        if idx % 2 == 0 {
                            format!("a{}", idx / 2)
                        } else {
                            format!("w{}", idx / 2)
                        }
                    });
                self.ports.push((name.clone(), "input".into(), dw));
                self.assign_lines.push(format!("  assign {w} = {name};"));
            }

            AtomOp::Const(v) => {
                self.assign_lines.push(format!("  assign {w} = {dw}'d{v};"));
            }

            AtomOp::Zero => {
                self.assign_lines.push(format!("  assign {w} = {dw}'d0;"));
            }

            AtomOp::One => {
                self.assign_lines.push(format!("  assign {w} = {dw}'d1;"));
            }

            AtomOp::Add | AtomOp::ReduceAdd => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {a} + {b};  // LUT adder"));
            }

            AtomOp::Mul | AtomOp::DspMul => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {a} * {b};  // DSP48 MUL"));
            }

            AtomOp::Mac | AtomOp::DspMac | AtomOp::Madd => {
                let x = child_wire(self, eg, node, 0, visited);
                let y = child_wire(self, eg, node, 1, visited);
                let z = child_wire(self, eg, node, 2, visited);
                self.assign_lines.push(format!("  assign {w} = ({x} * {y}) + {z};  // DSP48 MAC"));
            }

            AtomOp::Pipe => {
                self.has_clk = true;
                let inp = child_wire(self, eg, node, 0, visited);
                let ff = format!("{w}_reg");
                self.ff_lines.push(format!("  logic signed [{dw}-1:0] {ff};"));
                self.ff_lines.push(format!("  always_ff @(posedge clk) begin"));
                self.ff_lines.push(format!("    if (!rst_n) {ff} <= {dw}'d0;"));
                self.ff_lines.push(format!("    else       {ff} <= {inp};"));
                self.ff_lines.push(format!("  end"));
                self.assign_lines.push(format!("  assign {w} = {ff};"));
            }

            AtomOp::AccStep => {
                let prev = child_wire(self, eg, node, 0, visited);
                let val = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {prev} + {val};  // acc step (combinational)"));
            }

            AtomOp::AccInit => {
                let init = child_wire(self, eg, node, 0, visited);
                self.assign_lines.push(format!("  assign {w} = {init};"));
            }

            AtomOp::ReduceMin => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = ({a} < {b}) ? {a} : {b};  // MIN"));
            }

            AtomOp::ReduceMax => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = ({a} > {b}) ? {a} : {b};  // MAX"));
            }

            AtomOp::Sub => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {a} - {b};  // subtract"));
            }

            AtomOp::Shl => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {a} << {b};  // shift left"));
            }

            AtomOp::Shr => {
                let a = child_wire(self, eg, node, 0, visited);
                let b = child_wire(self, eg, node, 1, visited);
                self.assign_lines.push(format!("  assign {w} = {a} >> {b};  // shift right"));
            }

            _ => {
                if node.children.len() >= 1 {
                    let a = child_wire(self, eg, node, 0, visited);
                    self.assign_lines.push(format!("  assign {w} = {a};  // {node:?}"));
                } else {
                    self.assign_lines.push(format!("  assign {w} = {dw}'d0;  // leaf {node:?}"));
                }
            }
        }

        w
    }

    pub fn generate(&self) -> String {
        let mut out = String::new();
        let dw = self.data_width;
        let mn = &self.module_name;

        out.push_str(&format!(
            "// Auto-generated by hwine-rs meta-op -> RTL generator\n"
        ));
        out.push_str(&format!("// Target: Xilinx 7-series / Intel Cyclone FPGA\n"));
        out.push_str(&format!("// Data width: {dw} bits\n\n"));
        out.push_str(&format!("module {mn} #(\n"));
        out.push_str(&format!("  parameter DATA_WIDTH = {dw}\n"));
        out.push_str(&format!(") (\n"));

        if self.has_clk {
            out.push_str("  input  logic clk,\n");
            out.push_str("  input  logic rst_n,\n");
        }

        for (i, (name, dir, w)) in self.ports.iter().enumerate() {
            // Input ports always have trailing comma (output follows)
            out.push_str(&format!("  {dir} logic signed [{w}-1:0] {name},\n"));
        }
        out.push_str(&format!("  output logic signed [{dw}-1:0] result\n"));
        out.push_str(");\n\n");

        // Internal wires
        let mut used: Vec<&String> = self.wires.values().collect();
        used.sort();
        for w in &used {
            out.push_str(&format!("  logic signed [{dw}-1:0] {w};\n"));
        }
        out.push('\n');

        // Sequential
        if !self.ff_lines.is_empty() {
            out.push_str("  // -- Sequential logic --\n");
            for line in &self.ff_lines {
                out.push_str(line);
                out.push('\n');
            }
            out.push('\n');
        }

        // Combinational
        out.push_str("  // -- Combinational logic --\n");
        for line in &self.assign_lines {
            out.push_str(line);
            out.push('\n');
        }
        out.push('\n');

        // Output
        let root = if self.root_wire.is_empty() {
            used.into_iter().next_back().map(|s| s.as_str()).unwrap_or("'0")
        } else {
            &self.root_wire
        };
        out.push_str(&format!("  assign result = {root};\n\n"));
        out.push_str("endmodule\n");

        out
    }
}

/// Generate RTL from e-graph extraction
pub fn generate_rtl(eg: &EGraph, target_cid: u32, module_name: &str, data_width: usize) -> String {
    let mut rtl_gen = RtlGen::new(module_name, data_width);
    let mut visited = HashMap::new();
    rtl_gen.emit_node(eg, target_cid, true, &mut visited);
    rtl_gen.generate()
}

/// Generate pipelined RTL by walking the original e-graph's extraction result
/// and inserting Pipe nodes at each computation level.
/// Level 0: only wrap non-leaf children (input-side pipelining)
/// Level 1: also wrap parent node (full pipelining)
pub fn generate_pipelined_rtl(eg: &EGraph, target_cid: u32, module_name: &str, data_width: usize) -> String {
    generate_pipelined_rtl_level(eg, target_cid, module_name, data_width, 0)
}

/// Fine-grained pipeline: register after EVERY arithmetic operation
pub fn generate_fine_pipelined_rtl(eg: &EGraph, target_cid: u32, module_name: &str, data_width: usize) -> String {
    generate_pipelined_rtl_level(eg, target_cid, module_name, data_width, 1)
}

fn generate_pipelined_rtl_level(eg: &EGraph, target_cid: u32, module_name: &str, data_width: usize, level: usize) -> String {
    fn walk_tree(
        eg: &EGraph,
        cid: u32,
        pipe_eg: &mut EGraph,
        visited: &mut std::collections::HashMap<u32, u32>,
        in_progress: &mut std::collections::HashSet<u32>,
        level: usize,
    ) -> u32 {
        if let Some(&pc) = visited.get(&cid) {
            return pc;
        }
        let (node, _) = eg.extract_optimal(cid, ExtractMode::MinDelay);
        if node.children.is_empty() {
            let pc = pipe_eg.add(node.clone());
            visited.insert(cid, pc);
            return pc;
        }
        // Mark as in-progress before recursing into children
        in_progress.insert(cid);
        let mut wrapped: Vec<u32> = Vec::with_capacity(node.children.len());
        for &c in node.children.iter() {
            if in_progress.contains(&c) {
                continue; // cycle detected, skip this child
            }
            let pid = walk_tree(eg, c, pipe_eg, visited, in_progress, level);
            let (child_node, _) = eg.extract_optimal(c, ExtractMode::MinDelay);
            if child_node.children.is_empty() {
                wrapped.push(pid);
            } else {
                wrapped.push(pipe_eg.add(ENode::new(AtomOp::Pipe, vec![pid], DataType::default())));
            }
        }
        in_progress.remove(&cid);
        let pc = pipe_eg.add(ENode::new(node.op, wrapped, node.dtype));
        visited.insert(cid, pc);
        // Fine-grained: also register the output of this node (if not root)
        if level >= 1 {
            pipe_eg.add(ENode::new(AtomOp::Pipe, vec![pc], DataType::default()))
        } else {
            pc
        }
    }

    let mut pipe_eg = EGraph::new();
    let mut visited = std::collections::HashMap::new();
    let mut in_progress = std::collections::HashSet::new();
    let piped_cid = walk_tree(eg, target_cid, &mut pipe_eg, &mut visited, &mut in_progress, level);
    let mut rtl_gen = RtlGen::new(module_name, data_width);
    let mut v2 = std::collections::HashMap::new();
    rtl_gen.emit_node(&pipe_eg, piped_cid, true, &mut v2);
    rtl_gen.generate()
}
