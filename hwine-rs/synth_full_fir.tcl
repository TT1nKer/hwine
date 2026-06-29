set sizes {6 13 20 41}
foreach n $sizes {
  foreach typ {serial tree pipe} {
    set top full_fir_${n}_${typ}
    set fname full_fir_${n}_${typ}.sv
    if {![file exists $fname]} { puts "=== $top NOT FOUND"; continue }
    read_verilog -sv $fname
    synth_design -top $top -flatten_hierarchy rebuilt
    puts "=== $top ==="
    report_timing -max_paths 1 -delay_type max
    puts "---"
  }
}
exit
