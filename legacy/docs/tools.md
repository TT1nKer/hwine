# Tool Usage Reference

## Verilator

Compiles SystemVerilog to C++ for fast simulation.

```bash
verilator --version
```

Flags:
- `--cc` — generate C++ output
- `--exe` — generate executable wrapper
- `--trace-fst` — enable FST waveform tracing
- `--timing` — enable timing constructs
- `-y <dir>` — search path for modules
- `--top-module <name>` — top-level module name
- `-Wall` — all warnings

## Icarus Verilog

For linting in VSCode (not for simulation in this project).

```bash
iverilog -g2012 -Y .sv -y rtl/ -o output.vvp source.sv
```

## Yosys

Logic synthesis — RTL to gate-level netlist.

```bash
yosys -p "read_verilog -sv file.sv; synth; show -format dot -prefix out"
```

Interactive TCL shell:
```tcl
read_verilog -sv file.sv
hierarchy -top top_module
proc
synth   # generic synthesis
show    # display circuit diagram
write_verilog output.v
```

## Surfer

Waveform viewer. Open `.fst` or `.vcd` files.

```bash
surfer build/sim.fst
```

## Verilator + Make integration

```makefile
VERILATOR = verilator
VFLAGS    = --cc --exe --trace-fst -Wall --timing
TOP       = top_module
SRCS      = $(wildcard rtl/*.sv)
TB        = tb/testbench.cpp

build/V$(TOP): $(SRCS) $(TB)
	$(VERILATOR) $(VFLAGS) --top-module $(TOP) $(SRCS) $(TB) -o $@
	$(MAKE) -C obj_dir -f V$(TOP).mk

sim: build/V$(TOP)
	./build/V$(TOP)
```
