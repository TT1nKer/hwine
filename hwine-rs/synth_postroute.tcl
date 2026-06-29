# Vivado full flow: synth → place → route for hwine benchmarks
set_part xc7vx485tffg1761-2
set outfile "E:/hwine_vivado/vivado_postroute.txt"
set fp [open $outfile w]
puts $fp "benchmark LUT FF DSP CARRY4 WNS TNS Fmax_MHz"
flush $fp

proc run_full {bm} {
    global fp
    puts "=== $bm (synth+place+route) ==="
    if {![file exists E:/hwine_vivado/${bm}.sv]} { puts $fp "$bm NOT_FOUND"; flush $fp; return }
    if {[get_designs -quiet] ne ""} { remove_design -all }
    
    read_verilog -sv E:/hwine_vivado/${bm}.sv
    synth_design -top $bm -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2
    opt_design
    place_design
    route_design
    
    # Post-route resources
    set lut   [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
    set ff    [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
    set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1}]]
    set carry [llength [get_cells -hier -filter {REF_NAME =~ CARRY4}]]
    
    # Timing
    set wns 0; set tns 0; set fmax 0
    if {[catch {
        report_timing_summary -file E:/hwine_vivado/timing_${bm}.rpt
        set wns [get_property WORST_SLACK [get_timing_paths -max_paths 1 -nworst 1]]
        set tns [get_property TOTAL_NEGATIVE_SLACK [get_timing_paths]]
        if {$wns < 10.0} { set fmax [expr {1000.0 / (10.0 - $wns)}] }
    } err]} {}
    
    set line [format "%s %d %d %d %d %.3f %.3f %.0f" $bm $lut $ff $dsp $carry $wns $tns $fmax]
    puts $fp $line
    puts "  $line"
    flush $fp
}

# Run on key benchmarks (skip large ones for speed)
foreach bm {bm_dct8 bm_fft_butterfly cmul_direct cmul_gauss bm_stencil2d bm_dot_8} {
    run_full $bm
}

close $fp
puts "DONE — post-route results in $outfile"
