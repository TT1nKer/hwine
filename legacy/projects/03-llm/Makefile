TOP  = spatial_map
SRCS = ../../lib/spatial/pipe.sv ../../lib/spatial/map.sv ../../lib/spatial/reduce.sv ../../lib/spatial/fork.sv ../../lib/spatial/join.sv ../../lib/spatial/delay.sv
TB   = tb/spatial_tb.sv

IVERILOG ?= iverilog
VVP      ?= vvp

BUILD_DIR = build

.PHONY: all sim wave clean

all: sim

sim: $(BUILD_DIR)/tb.vvp
	$(VVP) $<

$(BUILD_DIR)/tb.vvp: $(SRCS) $(TB)
	mkdir -p $(BUILD_DIR)
	$(IVERILOG) -g2012 -Wall -o $@ $(SRCS) $(TB)

wave:
	surfer $(BUILD_DIR)/sim.vcd

clean:
	rm -rf $(BUILD_DIR)
