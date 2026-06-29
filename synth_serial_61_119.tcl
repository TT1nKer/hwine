read_verilog -sv { rtl_serial_fir_61.sv rtl_serial_fir_119.sv }
synth_design -top serial_fir_61 -flatten_hierarchy rebuilt
puts "=== SERIAL_61 ==="
report_timing -max_paths 1 -delay_type max
synth_design -top serial_fir_119 -flatten_hierarchy rebuilt
puts "=== SERIAL_119 ==="
report_timing -max_paths 1 -delay_type max
report_utilization
exit
