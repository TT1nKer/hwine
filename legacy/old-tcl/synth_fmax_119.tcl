read_verilog -sv { rtl_pipe_fir_119.sv }
synth_design -top pipe_fir_119 -flatten_hierarchy rebuilt
puts "=== PIPE_119 ==="
report_timing -max_paths 1 -delay_type max
exit
