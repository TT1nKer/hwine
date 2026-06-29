read_verilog -sv { hwine_fine_fir6.sv hwine_fine_add6.sv }
synth_design -top hwine_fine_fir6 -flatten_hierarchy rebuilt
puts "=== HWiNE FINE FIR6 ==="
report_utilization -name HFF6
report_timing -max_paths 1 -delay_type max
synth_design -top hwine_fine_add6 -flatten_hierarchy rebuilt
puts "=== HWiNE FINE ADD6 ==="
report_utilization -name HFA6
report_timing -max_paths 1 -delay_type max
exit
