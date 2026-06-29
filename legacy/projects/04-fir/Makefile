TOP  = fir_parallel
SRCS = $(wildcard rtl/*.sv)
TB   = tb/fir_tb.sv

IVERILOG ?= iverilog
VVP      ?= vvp

BUILD_DIR = build

.PHONY: all sim wave syn_s syn_p clean

all: sim

sim: $(BUILD_DIR)/tb.vvp
	$(VVP) $<

$(BUILD_DIR)/tb.vvp: $(SRCS) $(TB)
	mkdir -p $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -o $@ $(SRCS) $(TB)

wave:
	surfer $(BUILD_DIR)/sim.vcd

syn_s:
	mkdir -p $(BUILD_DIR)/synth_s
	yosys -p "read_verilog -sv rtl/fir_serial.sv; hierarchy -top fir_serial; proc; synth; stat" 2>&1

syn_p:
	mkdir -p $(BUILD_DIR)/synth_p
	yosys -p "read_verilog -sv rtl/fir_parallel.sv; hierarchy -top fir_parallel; proc; synth; stat" 2>&1

clean:
	rm -rf $(BUILD_DIR)
