// Vivado TCL script auto-generation
// Produces synth_design + report_utilization TCL from RTL metadata.
use crate::egraph::EGraph;
use crate::ir::ENode;

/// Generate a Vivado synthesis TCL script for a design.
/// Returns TCL source that can be saved to a .tcl file and run with `vivado -mode batch`.
pub fn generate_synth_tcl(
    module_name: &str,
    sv_file: &str,
    part: &str,
    out_report: &str,
) -> String {
    format!(
        r#"# Auto-generated Vivado synthesis script for {module_name}
set_part {part}
read_verilog -sv {sv_file}
synth_design -top {module_name} -flatten_hierarchy rebuilt -part {part}

# Resource utilization
set lut   [llength [get_cells -hier -filter {{REF_NAME =~ LUT*}} -quiet]]
set ff    [llength [get_cells -hier -filter {{REF_NAME =~ FD* || REF_NAME =~ FDRE*}} -quiet]]
set dsp   [llength [get_cells -hier -filter {{REF_NAME =~ DSP48E1}} -quiet]]
set carry [llength [get_cells -hier -filter {{REF_NAME =~ CARRY4}} -quiet]]

set fp [open {out_report} w]
puts $fp "module=${{module_name}}"
puts $fp "LUT=$lut"
puts $fp "FF=$ff"
puts $fp "DSP=$dsp"
puts $fp "CARRY4=$carry"
close $fp

puts "DONE — results in {out_report}"
"#,
        module_name = module_name,
        sv_file = sv_file,
        part = part,
        out_report = out_report,
    )
}

/// Compute a reasonable part based on module complexity (heuristic).
pub fn suggest_part(eg: &EGraph, node: &ENode, _data_width: usize) -> &'static str {
    let class_count = eg.n_classes();
    if class_count > 200 {
        "xc7vx485tffg1761-2" // bigger designs → Virtex-7
    } else {
        "xc7a100tcsg324-1" // smaller designs → Artix-7
    }
}
