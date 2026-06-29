# hwine Vivado synthesis script — tree_mac_16
set part xc7z020clg400-1
set top tree_mac_16

create_project hwine_mac16 ./hwine_mac16_proj -part $part -force
add_files -norecurse {tree_mac_16.sv serial_mac_16.sv}
set_property top $top [current_fileset]

# Timing constraint: 200MHz (5ns) — for pipelined designs
if {[llength [get_ports -quiet clk]] > 0} {
    create_clock -period 5.000 -name clk [get_ports clk]
}

# Synthesize
synth_design -top $top -part $part -flatten_hierarchy rebuilt

# Reports
report_utilization -file util_${top}.rpt
report_timing_summary -file timing_${top}.rpt -max_paths 10

# Run implementation
opt_design
place_design
route_design

report_utilization -file util_impl_${top}.rpt
report_timing_summary -file timing_impl_${top}.rpt -max_paths 10

puts "=================================="
puts " hwine synthesis complete: $top"
puts "=================================="
