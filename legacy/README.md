# hwine

**hardware is not enough** — and neither is hwine.

An AI-driven hardware development project.
The AI writes SystemVerilog, runs simulations, inspects waveforms, synthesizes to gates, and iterates based on results.

## Getting Started

```bash
# Run the first project (basic gates, adder, DFF, counter)
make -C projects/01-gates sim

# View waveforms
make -C projects/01-gates wave

# See the synthesized gate-level netlist
make -C projects/01-gates syn
```

## Project Layout

```
projects/<name>/      hardware designs
  rtl/                SystemVerilog sources (*.sv)
  tb/                 C++ testbenches for Verilator (*.cpp)
  Makefile            project build rules

lib/                  reusable components (FIFO, UART, AXI, etc.)
docs/                 AI learning reference
scripts/              shared build rules
```

## Tools

- **Verilator** — fast SystemVerilog simulator (SV → C++ → native binary)
- **Yosys** — logic synthesis (RTL → gate netlist)
- **Surfer** — waveform viewer
- **Icarus Verilog** — linting in VSCode
