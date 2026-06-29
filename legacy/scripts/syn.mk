# Shared synthesis rules for Yosys.
# Include this from project Makefiles.
#
# Requires:
#   TOP  = top module name
#   SRCS = list of .sv source files

YOSYS     ?= yosys
SYNTH_DIR ?= build/synth

.PHONY: syn show_syn clean_syn

syn:
	mkdir -p $(SYNTH_DIR)
	$(YOSYS) -p "read_verilog -sv $(SRCS); hierarchy -top $(TOP); proc; synth; write_verilog $(SYNTH_DIR)/$(TOP)_synth.v"

show_syn:
	mkdir -p $(SYNTH_DIR)
	$(YOSYS) -p "read_verilog -sv $(SRCS); hierarchy -top $(TOP); proc; synth; show -format dot -prefix $(SYNTH_DIR)/$(TOP)_synth" > /dev/null 2>&1
	cat $(SYNTH_DIR)/$(TOP)_synth.dot | head -5
	@echo "DOT file written to $(SYNTH_DIR)/$(TOP)_synth.dot (preview above)"

clean_syn:
	rm -rf $(SYNTH_DIR)
