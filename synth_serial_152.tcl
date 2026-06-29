read_verilog -sv { rtl_serial_fir_152.sv }
synth_design -top serial_fir_152 -flatten_hierarchy rebuilt
puts "=== SERIAL_152 ==="
report_timing -max_paths 1 -delay_type max
exit
