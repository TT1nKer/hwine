set part xc7z020clg400-1
create_project hwine_mac_16 ./hwine_mac_16_vivado -part $part -force
add_files out/hwine_mac_16.sv
set_property top hwine_mac_16 [current_fileset]
create_clock -period 5.0 [get_ports clk]
synth_design -top hwine_mac_16 -part $part
report_utilization -file utilization_hwine_mac_16.rpt
report_timing_summary -file timing_hwine_mac_16.rpt
puts "Synthesis complete for hwine_mac_16"
