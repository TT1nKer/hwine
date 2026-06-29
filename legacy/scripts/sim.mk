# Shared simulation rules for Verilator-based projects.
# Include this from project Makefiles.
#
# Required variables:
#   TOP    = top module name (used for binary naming, optional)
#   SRCS   = list of .sv source files
#   TB     = C++ testbench file path

VERILATOR ?= verilator
VFLAGS    ?= --cc --exe --trace-fst -Wall --timing

BUILD_DIR ?= build

.PHONY: sim wave clean_sim

VTOP_CPP = $(BUILD_DIR)/V$(TOP)__ALL.cpp

sim: $(VTOP_CPP)
	./$(VTOP_CPP)

$(VTOP_CPP): $(SRCS) $(TB)
	mkdir -p $(BUILD_DIR)
	$(VERILATOR) $(VFLAGS) \
		--Mdir $(BUILD_DIR) \
		--exe $(TB) \
		$(SRCS)
	$(MAKE) -C $(BUILD_DIR) -f Vtop.mk
	@# Rename the binary for convenience
	mv $(BUILD_DIR)/Vtop $(VTOP_CPP) 2>/dev/null || true

wave:
	surfer $(BUILD_DIR)/sim.fst

clean_sim:
	rm -rf $(BUILD_DIR)
