# Spatial Primitives

## Philosophy

No schedule. Only topology. Computation is expressed by connecting spatial
units with FIFOs. Each unit is a deterministic hardware template. Parameters
set parallelism, depth, and buffer sizes. Timing is emergent from the graph.
Backpressure propagates automatically through valid/ready handshakes.

## Core Primitives

Every primitive has:

- **Ports**: input streams and output streams
- **Valid/Ready**: standard AXI-style handshake on every port
- **Latency model**: cycles from first input valid to first output valid
- **Throughput model**: inputs consumed per cycle, outputs produced per cycle
- **Area model**: rough LUT + FF + DSP count (vendor-agnostic estimates)
- **Hardware template**: a deterministically-expandable RTL pattern

### 1. Map(f, p=1, buf_in=0, buf_out=0)

```
         ┌─────────────────────────┐
  in ───→│  Map(f, parallelism=p)  │───→ out
         └─────────────────────────┘
```

**Behavior**: Apply function `f` to every element. With `p > 1`, `p` copies of
`f` run in parallel on a striped input stream. Input is distributed round-robin
across copies. Output is collected in order (preserves ordering).

**Hardware**:
```
  p=1:  f instance, optionally piped through buf_in/buf_out FIFOs
  p>1:  demux(1→p) → p× f instances → ordered merge(p→1)
        ordered merge = tag-based reorder buffer (depth = buf_out)
```

**Parameters**:
| param | meaning | hardware effect |
|-------|---------|-----------------|
| p | parallelism copies | p × area(f), p / latency(f) throughput |
| buf_in | input FIFO depth | backpressure absorption |
| buf_out | output reorder buffer depth | out-of-order completion tolerance |

**Area**: `p · area(f) + area(demux) + area(reorder) + (buf_in + buf_out) · width`

**Latency** (first in → first out): `latency(f) + buf_in + buf_out`

**Throughput**: `p / latency(f)` elements per cycle (steady state)

---

### 2. Reduce(op, tree, buf_in=0)

```
         ┌─────────────────────────┐
  in ───→│  Reduce(op, tree_depth)  │───→ out
         └─────────────────────────┘
```

**Behavior**: Reduce a stream of length N to a single value using binary
operator `op` (must be associative). `tree` = 0 means serial accumulation.
`tree` = n means n-level pipelined tree.

**Hardware**:
```
  serial:  acc ← op(acc, in_elem)
  tree=1:  pairwise combine, 1 level, N/2 op instances
  tree=2:  2-level tree, N/2 + N/4 op instances
  ...
```

**Parameters**:
| param | meaning | hardware effect |
|-------|---------|-----------------|
| op | associative binary operator | 1 or more op instances |
| tree | reduction tree depth | tree ≥ 1 → hardware tree |

**Area**: `(N - 1) · area(op)` for fully unrolled tree. For pipelined: plus
`tree · N/2 · width` registers between levels.

**Latency**: `tree · latency(op)` for fully unrolled; `tree + latency(op)` for pipelined.

**Throughput**: 1 result per N elements per cycle. Fully pipelined:
1 result per cycle (pipelined tree, overlapping reductions).

---

### 3. Pipe(A, B, depth=2)

```
         ┌──────────┐     ┌──────────┐
  in ───→│    A     │────→│  FIFO(d) │───→ out
         └──────────┘     └──────────┘
```

**Behavior**: Connect primitive A's output to primitive B's input through a
FIFO of depth `depth`. Backpressure propagates automatically: if B is not
ready, FIFO fills up; if FIFO is full, A stalls.

**Hardware**: Standard dual-clock or single-clock FIFO with valid/ready
handshake. depth=0 means direct wire (no register, combinational path).

**Parameters**:
| param | meaning |
|-------|---------|
| A, B | upstream/downstream primitives |
| depth | FIFO depth (0 = wire, ≥1 = registered FIFO) |

**Area**: `depth · width(data) · area(FF) + area(FIFO_ctrl)`

**Latency contribution**: `depth` cycles

**Critical rule**: A's output width must equal B's input width.

---

### 4. Fork(n, method="broadcast")

```
                           ┌─→ out_0
  in ───→ Fork(n=3) ──────┼─→ out_1
                           └─→ out_2
```

**Behavior**: Replicate input stream to `n` identical output streams.
- `broadcast`: all outputs get every input element
- `round_robin`: elements distributed to outputs in order (like Map demux)

**Hardware**: n copies of input data wire.

**Throughput**: 1 element per cycle (all consumers must keep up, or the
slowest consumer throttles the input).

---

### 5. Join(n, method="sync")

```
  in_0 ──┐
  in_1 ──┤──→ Join(n=3, sync) ──→ out
  in_2 ──┘
```

**Behavior**: Combine `n` input streams into one output stream.
- `sync`: output fires only when ALL n inputs have valid data
- `priority`: if multiple inputs valid, pick the one with lowest index
- `round_robin`: fair arbitration among ready inputs

**Hardware**: n-input AND gate (sync), priority encoder (priority), or
round-robin arbiter (round_robin).

---

### 6. Stencil(window_h×window_w, line_width, buf_lines)

```
         ┌───────────────────────────────────┐
  in ───→│  Stencil(3×3, line_width=1920)     │───→ out
         └───────────────────────────────────┘
                      ↓
         [line buffer 0] → [line buffer 1]
                      ↓
              [3×3 register window]
                      ↓
                 [kernel op]
```

**Behavior**: Sliding window over a 2D stream (image rows). `line_width`
specifies pixels per line. `buf_lines` = window_h - 1 line buffers.

**Hardware**:
- `buf_lines` line buffers (shift regs of length `line_width`)
- `window_h × window_w` register window
- Kernel computation unit

**Latency**: `buf_lines · line_width + window_h` cycles (line fill time)

**Throughput**: 1 pixel per cycle (steady state, after initial fill)

**Area**: `buf_lines · line_width · width(data) · area(FF) + window_area`

---

### 7. Delay(cycles)

```
  in ───→ [reg] → [reg] → ... → [reg] ───→ out
             0        1            n-1
```

**Behavior**: Shift input through `cycles` register stages. Pure delay,
no computation.

**Hardware**: Shift register of depth `cycles`.

**Latency**: exactly `cycles`. Throughput: 1 per cycle.

---

### 8. Buffer(depth)

```
         ┌────────────┐
  in ───→│ Buffer(d=4) │───→ out
         └────────────┘
```

**Behavior**: Elastic buffer. Decouples producer and consumer rates. If
consumer is slow, buffer fills. If producer is slow, buffer drains.

**Hardware**: Parameterized FIFO. Different from Pipe: Pipe connects two
specific primitives; Buffer is a standalone component.

---

## Composition Rules

Primitives compose by connecting an output to an input. The connection is
valid if:
1. Data widths match
2. No combinational cycle is formed (Delay must break all cycles)
3. Fork → multiple consumers each consume at their own rate (slowest throttles)

## RTL Template Contract

Every primitive MUST produce a Verilator-simulatable SystemVerilog module
with exactly this interface:

```systemverilog
module spatial_map #(
    parameter FUNC_NAME = "add",   // function to apply
    parameter PARALLELISM = 1,
    parameter DATA_WIDTH = 32,
    parameter BUF_IN = 0,
    parameter BUF_OUT = 0
) (
    input  logic clk,
    input  logic rst_n,

    // Input stream (valid/ready handshake)
    input  logic             in_valid,
    input  logic [DATA_WIDTH-1:0] in_data,
    output logic             in_ready,

    // Output stream
    output logic             out_valid,
    output logic [DATA_WIDTH-1:0] out_data,
    input  logic             out_ready
);
```

Every variant with different parameters produces a synthesizable, deterministic
RTL blob. No heuristic, no "compiler optimization," no surprise.

## What the "Scheduler" Becomes

With this model, scheduling is NOT:

- "Which cycle does this operation execute in?" (traditional HLS)
- "When is data available?" (dynamic scheduling)

Instead, scheduling IS:

- **Choosing parameter values**: p for Map, tree for Reduce, depth for Pipe
- **Given constraints**: area budget, target frequency, I/O bandwidth
- **Objective**: maximize throughput, or minimize latency, or minimize area

This is a **parameter optimization problem** over the spatial graph. It can
be solved via:
- Analytical closed-form solution (when the graph is simple)
- LP/MILP (when there are discrete choices and budget constraints)
- Iterative greedy refinement (for complex graphs)

The key insight: **the scheduling difficulty has been moved from the runtime
of the compiler to the design of the language.** If the primitives are
well-chosen, the optimization is straightforward.
