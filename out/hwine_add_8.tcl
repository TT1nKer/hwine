set part xc7z020clg400-1
create_project hwine_add_8 ./hwine_add_8_vivado -part $part -force
add_files out/hwine_add_8.sv
set_property top hwine_add_8 [current_fileset]
create_clock -period 5.0 [get_ports clk]
synth_design -top hwine_add_8 -part $part
report_utilization -file utilization_hwine_add_8.rpt
report_timing_summary -file timing_hwine_add_8.rpt
puts "Synthesis complete for hwine_add_8"
