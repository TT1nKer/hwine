TOP  = gates
SRCS = $(wildcard rtl/*.sv)
TB   = tb/gates_tb.sv

IVERILOG ?= iverilog
VVP      ?= vvp

BUILD_DIR = build

.PHONY: all sim wave syn clean

all: sim

sim: $(BUILD_DIR)/tb.vvp
	$(VVP) $<

$(BUILD_DIR)/tb.vvp: $(SRCS) $(TB)
	mkdir -p $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -o $@ $(SRCS) $(TB)

wave:
	surfer $(BUILD_DIR)/sim.vcd

syn:
	mkdir -p $(BUILD_DIR)/synth
	yosys -p "read_verilog -sv $(SRCS); hierarchy; proc; synth; show -format dot -prefix $(BUILD_DIR)/synth/gates_synth"

clean:
	rm -rf $(BUILD_DIR)
