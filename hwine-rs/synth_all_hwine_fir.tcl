set sizes {6 10 13 20 28 41 61 71 119 152}
foreach n $sizes {
  foreach typ {comb fine} {
    set top hwine_${typ}_fir_${n}
    set fname hwine_fir_${n}_${typ}.sv
    if {![file exists $fname]} { puts "SKIP $fname"; continue }
    read_verilog -sv $fname
    synth_design -top $top -flatten_hierarchy rebuilt
    puts "=== $top ==="
    report_utilization -name U_${top}
    report_timing -max_paths 1 -delay_type max
    puts "---"
  }
}
exit
