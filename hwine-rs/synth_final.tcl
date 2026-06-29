set sizes {6 10 13 20 28 41 61 71 119 152}
foreach n $sizes {
  set f E:/hwine_vivado/hwine_fir_all/hwine_fir_${n}_fine.sv
  if {![file exists $f]} { puts "MISS $f"; continue }
  read_verilog -sv $f
  synth_design -top hwine_fir_${n} -flatten_hierarchy rebuilt
  report_utilization
  report_timing -max_paths 1 -delay_type max
  set cp [get_property SLACK [get_timing_paths -max_paths 1]]
  puts "RESULT_FIR${n} LUT=[get_property LUT_COUNT [get_design]] FF=[get_property FF_COUNT [get_design]] CARRY4=[get_property CARRY4_COUNT [get_design]] DSP=[get_property DSP_COUNT [get_design]] FMAX=[expr {1.0e3 / ($cp > 0 ? ($cp + 3.25) : 3.25)}]"
}
exit
