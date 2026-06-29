TOP  = dot_int4_tile
SRCS = rtl/dot_int4_tile.sv
TB   = tb/dot_tile_tb_gen.sv

IVERILOG ?= iverilog
VVP      ?= vvp

BUILD_DIR = build

.PHONY: all sim wave syn clean vectors

all: vectors sim

vectors:
	cd ../.. && python3 -m tools.llmsim.gen_vectors projects/05-dotile/$(TB)

sim: $(BUILD_DIR)/tb.vvp
	$(VVP) $<

$(BUILD_DIR)/tb.vvp: $(SRCS) $(TB)
	mkdir -p $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -o $@ $(SRCS) $(TB)

wave:
	surfer $(BUILD_DIR)/sim.vcd

syn:
	mkdir -p $(BUILD_DIR)/synth
	yosys -p "read_verilog -sv rtl/dot_int4_tile.sv; hierarchy -top dot_int4_tile; proc; synth; stat" 2>&1 | tee $(BUILD_DIR)/synth/report.txt

clean:
	rm -rf $(BUILD_DIR)

