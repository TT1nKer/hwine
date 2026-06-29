# Post-route batch: FFT butterfly, Stencil2D (resources only)
set_part xc7vx485tffg1761-2
set outfile "E:/hwine_vivado/vivado_pr_batch.txt"
set fp [open $outfile w]
puts $fp "benchmark LUT FF DSP CARRY4"
flush $fp

proc pr_one {bm} {
    global fp
    puts "=== $bm ==="
    if {![file exists E:/hwine_vivado/${bm}.sv]} { puts $fp "$bm NOT_FOUND"; flush $fp; return }
    if {[get_designs -quiet] ne ""} { remove_design -all }
    read_verilog -sv E:/hwine_vivado/${bm}.sv
    synth_design -top $bm -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2
    opt_design
    place_design
    route_design
    set lut   [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
    set ff    [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
    set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1}]]
    set carry [llength [get_cells -hier -filter {REF_NAME =~ CARRY4}]]
    set line "$bm $lut $ff $dsp $carry"
    puts $fp $line
    puts "  $line"
    flush $fp
}

foreach bm {bm_fft_butterfly cmul_direct cmul_gauss bm_stencil2d bm_dot_8} {
    pr_one $bm
}

close $fp
puts "DONE — results in $outfile"
