# hwine Vivado Synthesis Pack

## Files
- `tree_mac_16.sv` — hwine e-graph optimized (6 levels, 4.8ns)
- `serial_mac_16.sv` — serial baseline (16 levels, 12.8ns)
- `synth.tcl` — Vivado synthesis script

## Run
```bash
vivado -mode batch -source synth.tcl
```

## Expected
- Yosys: 232 cells (ADD tree), 1499 cells (MAC tree)
- Iverilog: PASS
- hwine analysis: depth 16→6 (2.7× speedup)

## Compare
Change `set top` to `serial_mac_16` for baseline synthesis.
