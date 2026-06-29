# hwine 长期愿景

## 三层架构

```
任务描述（计算图）
    ↓
e-graph 重写：自动探索等价结构（结合律、分配律、流水线、重定时）
    ↓
多目标提取：面积 vs 延迟 vs 吞吐量的 Pareto 前沿
    ↓
生成可综合 RTL
```

## 当前完成

- ✅ 结合律（serial → tree）：ADD/MIN/MAX/SCAN 四种操作验证
- ✅ Rust e-graph 引擎：N=512 秒级，比 Python 快 500×
- ✅ RTL 生成：SystemVerilog + Vivado TCL
- ✅ Yosys 综合验证：面积 ±0%，深度 12.7×
- ✅ MAC 算子：ACC_STEP 展平 + MAC 拆合

## 待完成（按优先级）

| 能力 | 做什么 | 难度 | 状态 |
|------|--------|------|------|
| 分配律 | (a+b)*c ↔ a*c + b*c，改变 DSP 数量 | 中 | 下一步 |
| 真实 cost model | 从 Yosys P&R 反标实际延迟和面积 | 中 | — |
| 重定时/流水线 | 自动插寄存器、平衡流水级 | 高 | — |
| 资源共享 | 多操作分时复用同一硬件 | 高 | — |
| Yosys plugin | 作为综合 pass 集成进 EDA 流程 | 中 | 进行中 |

## 竞争定位

- ROVER (Intel): 4 年，做了结合律 + bitvector 规则验证
- PrefixRL (NVIDIA): RL 搜索前级图，已量产 Hopper GPU
- hwine 的差异化：无需训练、声明式规则、跨算子复用、开源

## 参考

- ROVER: RTL Optimization via Verified E-Graph Rewriting (ISCA 2024)
- PrefixRL: Optimization of Parallel Prefix Circuits using Deep RL (DAC 2021)
- Guided Equality Saturation (POPL 2024)
