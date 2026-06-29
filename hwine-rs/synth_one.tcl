# synth_one.tcl — synthesize a single benchmark
# Usage: vivado -mode batch -source synth_one.tcl -tclargs <benchmark_name>
set bm [lindex $argv 0]
set outfile "E:/hwine_vivado/vivado_${bm}.txt"
set fp [open $outfile w]

read_verilog -sv E:/hwine_vivado/${bm}.sv
synth_design -top $bm -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2

set lut   [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
set ff    [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1}]]
set carry [llength [get_cells -hier -filter {REF_NAME =~ CARRY4}]]

set line "$bm $lut $ff $dsp $carry"
puts $fp $line
puts "RESULT: $line"
close $fp
