# Synthesis-only timing comparison: serial vs tree vs pipelined
# 20-tap FIR adder tree

read_verilog -sv {
    rtl_serial_fir_20.sv
    rtl_tree_fir_20.sv
    rtl_pipe_fir_20.sv
}

# Serial (combinational)
synth_design -top serial_fir_20 -flatten_hierarchy rebuilt
puts "=== SERIAL_20 ==="
report_timing -max_paths 1 -delay_type max
report_timing -max_paths 1 -delay_type min
set serial_20_tns [get_property SLACK [get_timing_paths -max_paths 1]]

# Tree (combinational)
synth_design -top tree_fir_20 -flatten_hierarchy rebuilt
puts "=== TREE_20 ==="
report_timing -max_paths 1 -delay_type max
report_timing -max_paths 1 -delay_type min

# Pipe (registered)
synth_design -top pipe_fir_20 -flatten_hierarchy rebuilt
puts "=== PIPE_20 ==="
report_timing -max_paths 1 -delay_type max
report_timing -max_paths 1 -delay_type min

exit
