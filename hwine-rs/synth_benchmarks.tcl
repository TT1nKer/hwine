# Vivado synthesis — hwine benchmarks (resources only)
set_part xc7vx485tffg1761-2
set outfile "E:/hwine_vivado/vivado_bench_results.txt"
set fp [open $outfile w]
puts $fp "name LUT FF DSP CARRY4"
flush $fp

proc do_synth {bm} {
    global fp
    puts "=== $bm ==="
    if {![file exists E:/hwine_vivado/${bm}.sv]} {
        puts $fp "$bm NOT_FOUND"
        flush $fp; return
    }
    if {[get_designs -quiet] ne ""} { remove_design -all }
    
    read_verilog -sv E:/hwine_vivado/${bm}.sv
    synth_design -top $bm -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2
    
    set lut   [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
    set ff    [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
    set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1}]]
    set carry [llength [get_cells -hier -filter {REF_NAME =~ CARRY4}]]
    
    set line "$bm $lut $ff $dsp $carry"
    puts $fp $line
    puts "  $line"
    flush $fp
}

foreach bm {bm_dct8 bm_dot_8 bm_dot_32 bm_fft_butterfly bm_stencil2d cmul_direct cmul_gauss} {
    do_synth $bm
}

close $fp
puts "DONE — results in $outfile"
