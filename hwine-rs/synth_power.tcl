# Power measurement on hwine designs
read_verilog -sv {
    hwine_fine_fir6.sv
    paper_naive_bal_20.sv
    paper_egraph_opt_20.sv
}
synth_design -top hwine_fine_fir6 -flatten_hierarchy rebuilt
puts "=== POWER FIR6 ==="
report_power
synth_design -top naive_bal_20 -flatten_hierarchy rebuilt
puts "=== POWER NAIVE20 ==="
report_power
synth_design -top egraph_opt_20 -flatten_hierarchy rebuilt
puts "=== POWER EGRAPH20 ==="
report_power
exit
