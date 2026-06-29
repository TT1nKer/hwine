read_verilog -sv { fir6_const_test.sv }
synth_design -top fir6_const -flatten_hierarchy rebuilt
puts "=== HWiNE CONST FIR6 ==="
report_utilization -name HWF6
report_timing -max_paths 1 -delay_type max
exit
