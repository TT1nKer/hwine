// Vivado TCL script auto-generation
// Produces synth_design + report_utilization + report_timing TCL from RTL metadata.
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
    let tcl = format!(
        r#"# Auto-generated Vivado synthesis script for {module}
set_part {part}
read_verilog -sv {sv}
synth_design -top {module} -flatten_hierarchy rebuilt -part {part}

# Resource utilization
set lut   [llength [get_cells -hier -filter {{REF_NAME =~ LUT*}} -quiet]]
set ff    [llength [get_cells -hier -filter {{REF_NAME =~ FD* || REF_NAME =~ FDRE*}} -quiet]]
set dsp   [llength [get_cells -hier -filter {{REF_NAME =~ DSP48E1}} -quiet]]
set carry [llength [get_cells -hier -filter {{REF_NAME =~ CARRY4}} -quiet]]

# Timing analysis
report_timing -delay_type max -max_paths 1 -name timing_max

# Extract Fmax from worst negative slack (WNS)
set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set period [get_property PERIOD [current_design]]
if {{ $period > 0 }} {{
    set fmax_mhz [expr {{ 1000.0 / ($period - $wns) }}]
}} else {{
    set fmax_mhz 0
}}

set fp [open {report} w]
puts $fp "module={module}"
puts $fp "LUT=$lut"
puts $fp "FF=$ff"
puts $fp "DSP=$dsp"
puts $fp "CARRY4=$carry"
puts $fp "WNS_ns=$wns"
puts $fp "Period_ns=$period"
puts $fp "Fmax_MHz=[format %.1f $fmax_mhz]"
close $fp

puts "DONE — results in {report}"
"#,
        module = module_name,
        sv = sv_file,
        part = part,
        report = out_report,
    );
    tcl
}

/// Generate a batch synthesis TCL that synthesizes multiple designs
/// and appends results to a CSV file.
pub fn generate_batch_tcl(
    designs: &[(&str, &str)],  // (module_name, sv_file_path)
    part: &str,
    csv_out: &str,
) -> String {
    let header = format!(
        r#"# Auto-generated batch synthesis script
# Synthesizes {} designs and writes CSV results
set_part {part}

set fp [open {csv} w]
puts $fp "module,LUT,FF,DSP,CARRY4,WNS_ns,Fmax_MHz"
close $fp
"#,
        designs.len(),
        part = part,
        csv = csv_out,
    );

    let mut tcl = header;
    for (module, sv_file) in designs {
        let block = format!(
            r#"
read_verilog -sv {sv}
synth_design -top {module} -flatten_hierarchy rebuilt -part {part}

set lut   [llength [get_cells -hier -filter {{REF_NAME =~ LUT*}} -quiet]]
set ff    [llength [get_cells -hier -filter {{REF_NAME =~ FD* || REF_NAME =~ FDRE*}} -quiet]]
set dsp   [llength [get_cells -hier -filter {{REF_NAME =~ DSP48E1}} -quiet]]
set carry [llength [get_cells -hier -filter {{REF_NAME =~ CARRY4}} -quiet]]

set wns [get_property SLACK [get_timing_paths -delay_type max -max_paths 1]]
set period [get_property PERIOD [current_design]]
if {{ $period > 0 }} {{
    set fmax_mhz [expr {{ 1000.0 / ($period - $wns) }}]
}} else {{
    set fmax_mhz 0
}}

set fp [open {csv} a]
puts $fp "{module},$lut,$ff,$dsp,$carry,$wns,[format %.1f $fmax_mhz]"
close $fp
"#,
            module = module,
            sv = sv_file,
            part = part,
            csv = csv_out,
        );
        tcl.push_str(&block);
    }

    tcl.push_str(&format!("\nputs \"DONE — all designs in {csv}\"\n", csv = csv_out));
    tcl
}

/// Compute a reasonable part based on module complexity (heuristic).
pub fn suggest_part(eg: &EGraph, _node: &ENode, _data_width: usize) -> &'static str {
    let class_count = eg.n_classes();
    if class_count > 200 {
        "xc7vx485tffg1761-2" // bigger designs → Virtex-7
    } else {
        "xc7a100tcsg324-1" // smaller designs → Artix-7
    }
}
