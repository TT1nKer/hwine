# hwine — Spatial Algebra Hardware Compiler
hwine = "hardware is not enough" (自指). 不是 C-to-hardware 编译器，只优化以空间原语表达的显式代数结构。

## 三层架构
- Layer 0: RISC Atom Space (`tools/risc-atom/`) — 34 个原子操作
- Layer 1: Spatial Primitives (`docs/spatial-primitives.md`) — 8 种空间原语
- Layer 2: RTL Projects (`projects/<name>/`) — SystemVerilog 实现

## 语言
SystemVerilog (`.sv`). `logic` 类型, `always_ff`/`always_comb`, 禁 `wire`/`reg`.

## 仿真与综合
- `make sim` → Verilator 编译 + 仿真, 生成 `.fst`
- `make wave` → surfer 查看波形
- `make syn` → Yosys 综合

## AI 规则
- 不写无 testbench 的模块
- 不用 wire/reg, 只用 logic
- always_comb 不用 always @(*)
- 分离 combinational 和 sequential 逻辑
- 显式 FSM 状态, 不全靠 reset
