read_verilog -sv {
    rtl_serial_fir_41.sv
    rtl_tree_fir_41.sv
    rtl_pipe_fir_41.sv
}
synth_design -top serial_fir_41 -flatten_hierarchy rebuilt
puts "=== SERIAL_41 ==="
report_timing -max_paths 1 -delay_type max
synth_design -top tree_fir_41 -flatten_hierarchy rebuilt
puts "=== TREE_41 ==="
report_timing -max_paths 1 -delay_type max
synth_design -top pipe_fir_41 -flatten_hierarchy rebuilt
puts "=== PIPE_41 ==="
report_timing -max_paths 1 -delay_type max
report_utilization -name CELL_41
exit
