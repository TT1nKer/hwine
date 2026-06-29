read_verilog -sv { hwine_fine_add6.sv }
synth_design -top hwine_fine_add6 -flatten_hierarchy rebuilt
puts "=== HWiNE FINE ADD6 ==="
report_utilization
report_timing -max_paths 1 -delay_type max
exit
