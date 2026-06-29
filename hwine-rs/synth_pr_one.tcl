# Minimal post-route — bm_dct8 (resources only, no clock)
set_part xc7vx485tffg1761-2
read_verilog -sv E:/hwine_vivado/bm_dct8.sv
synth_design -top bm_dct8 -flatten_hierarchy rebuilt -part xc7vx485tffg1761-2
opt_design
place_design
route_design
set lut   [llength [get_cells -hier -filter {REF_NAME =~ LUT*}]]
set ff    [llength [get_cells -hier -filter {REF_NAME =~ FD*}]]
set dsp   [llength [get_cells -hier -filter {REF_NAME =~ DSP48E1}]]
set carry [llength [get_cells -hier -filter {REF_NAME =~ CARRY4}]]
set f [open E:/hwine_vivado/vivado_pr_dct8.txt w]
puts $f "$lut $ff $dsp $carry"; close $f
puts "POST-ROUTE: LUT=$lut FF=$ff DSP=$dsp CARRY=$carry"
