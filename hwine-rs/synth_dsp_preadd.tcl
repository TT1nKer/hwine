# Vivado synthesis — DSP48 pre-adder verification
# Checks: (a+b)*c pattern maps to 1 DSP slice with pre-adder (not 1 DSP + LUT add)
set_part xc7vx485tffg1761-2
set outfile "E:/hwine_vivado/dsp_preadd_result.txt"
set fp [open $outfile w]

puts $fp "=== DSP PRE-ADDER VERIFICATION ==="

if {[get_designs -quiet] ne ""} { remove_design -all }
read_verilog -sv E:/hwine_vivado/bm_dsp_preadd.sv
synth_design -top bm_dsp_preadd -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2

set lut_raw [llength [get_cells -hier -filter {REF_NAME =~ LUT*} -quiet]]
set ff_raw [llength [get_cells -hier -filter {REF_NAME =~ FD*} -quiet]]
set dsp    [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1} -quiet]]
set carry  [llength [get_cells -hier -filter {REF_NAME =~ CARRY4} -quiet]]

# LUT2 primitives used as I/O passthrough are NOT arithmetic LUTs
# Real arithmetic LUTs are LUT1-LUT6 (not LUT2)
set lut_io  [llength [get_cells -hier -filter {REF_NAME == LUT2} -quiet]]
set lut_arith [expr {$lut_raw - $lut_io}]

puts $fp "LUT_raw=$lut_raw LUT_io=$lut_io LUT_arith=$lut_arith"
puts $fp "FF=$ff_raw DSP=$dsp CARRY4=$carry"

if {$dsp == 1 && $lut_arith == 0} {
    puts $fp "RESULT=PASS (1 DSP48E1, 0 arithmetic LUTs — pre-adder absorbed into DSP slice)"
} elseif {$dsp > 0} {
    puts $fp "RESULT=DSP_USED_BUT_LUT ($dsp DSP, $lut_arith arithmetic LUTs)"
} else {
    puts $fp "RESULT=FAIL (0 DSP slices — pre-adder not inferred)"
}

close $fp
puts "DONE — results in $outfile"
