read_verilog -sv { hwine_const_fir6_pipe.sv }
synth_design -top hwine_const_fir6_pipe -flatten_hierarchy rebuilt
puts "=== HWiNE PIPE CONST FIR6 ==="
report_utilization -name HPF6
report_timing -max_paths 1 -delay_type max
exit
