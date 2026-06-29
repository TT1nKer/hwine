"""
Meta-operation IR: data-level atoms for quantization hardware on FPGA.

FPGA cost model lives here — LUT/DSP/BRAM/FF estimates + routing penalty.
Pipeline-aware: PIPE and DELAY atoms for register insertion.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Any


class AtomOp(Enum):
    # ---- Data compute ----
    MUL    = auto()  # multiply: (a, b) -> data  —→ DSP on FPGA
    ADD    = auto()  # add: (a, b) -> data       —→ LUT on FPGA
    MAC    = auto()  # fused multiply-accumulate: (w, a, acc) —→ DSP cascade
    MADD   = auto()  # multiply-add: (a, b, c) -> a*b+c
    SHL    = auto()
    SHR    = auto()
    SAT    = auto()
    ROUND  = auto()

    # ---- Reduction ----
    REDUCE_ADD = auto()
    REDUCE_MAX = auto()
    REDUCE_MIN = auto()

    # ---- Prefix scan ----
    SCAN = auto()

    # ---- Data layout ----
    PACK    = auto()
    UNPACK  = auto()
    CONCAT  = auto()
    SLICE   = auto()
    EXTRACT = auto()

    # ---- Data movement ----
    BUFFER    = auto()  # FIFO buffer: (data, depth)
    ROUTE     = auto()  # route to dest: (data, src, dst)
    BROADCAST = auto()  # fan-out: (data, n)

    # ---- Pipeline (FPGA-specific) ----
    PIPE      = auto()  # pipeline register stage: (data) -> data (1 cycle latency, 0 LUT, 1 FF)
    DELAY     = auto()  # shift register delay: (data, cycles) -> data

    # ---- FPGA-native DSP annotations ----
    DSP_MUL   = auto()  # MUL mapped to DSP slice
    DSP_MAC   = auto()  # MAC mapped to DSP cascade chain

    # ---- Quantization ----
    QUANT     = auto()
    DEQUANT   = auto()
    DEQUANT_W = auto()

    # ---- Identity/literals ----
    CONST   = auto()
    VAR     = auto()
    STR_LIT = auto()
    ZERO    = auto()
    ONE     = auto()

    # ---- Accumulator ----
    ACC_INIT  = auto()
    ACC_STEP  = auto()
    ACC_READ  = auto()
    ACC_RESET = auto()


# ── Algebraic properties ──

ASSOCIATIVE_OPS = {
    AtomOp.ADD, AtomOp.MUL, AtomOp.MADD,
    AtomOp.REDUCE_ADD, AtomOp.REDUCE_MAX, AtomOp.REDUCE_MIN,
    AtomOp.SCAN,  # SCAN(ADD) is associative: (s0+v1)+v2 = s0+(v1+v2)
}

COMMUTATIVE_OPS = {AtomOp.ADD, AtomOp.MUL}

IDENTITY_ELEMENTS = {AtomOp.ADD: 0, AtomOp.MUL: 1}


# ═══════════════════════════════════════════════════════════
# FPGA Cost Model — calibrated for Xilinx 7-series / Intel Cyclone
# ═══════════════════════════════════════════════════════════

# How many LUTs (6-input) does this op consume?
FPGA_LUT_COST = {
    AtomOp.ADD: 0.5,         # half a LUT per bit; for 8-bit ≈ 4 LUTs
    AtomOp.MUL: 0,           # goes to DSP (counted separately)
    AtomOp.MAC: 0,           # DSP cascade
    AtomOp.MADD: 0,          # DSP
    AtomOp.DSP_MUL: 0,       # explicit DSP
    AtomOp.DSP_MAC: 0,       # explicit DSP cascade
    AtomOp.SHL: 0,           # wiring only
    AtomOp.SHR: 0,           # wiring only
    AtomOp.SAT: 1,           # comparator logic
    AtomOp.ROUND: 1,
    AtomOp.REDUCE_ADD: 0.5,  # per element (tree internal)
    AtomOp.REDUCE_MAX: 0.5,
    AtomOp.REDUCE_MIN: 0.5,
    AtomOp.SCAN: 2,
    AtomOp.PACK: 0,          # pure wiring
    AtomOp.UNPACK: 0,
    AtomOp.CONCAT: 0,
    AtomOp.SLICE: 0,
    AtomOp.EXTRACT: 0,
    AtomOp.BUFFER: 0,        # flip-flops (counted separately)
    AtomOp.ROUTE: 0,         # routing cost handled separately
    AtomOp.BROADCAST: 0,
    AtomOp.PIPE: 0,          # 0 LUT, 1 FF per bit (counted in FF)
    AtomOp.DELAY: 0,         # shift register
    AtomOp.QUANT: 1,
    AtomOp.DEQUANT: 1,
    AtomOp.DEQUANT_W: 1,
    AtomOp.CONST: 0,
    AtomOp.VAR: 0,
    AtomOp.STR_LIT: 0,
    AtomOp.ZERO: 0,
    AtomOp.ONE: 0,
    AtomOp.ACC_INIT: 1,
    AtomOp.ACC_STEP: 1,
    AtomOp.ACC_READ: 0,
    AtomOp.ACC_RESET: 1,
}

# DSP48 blocks consumed
FPGA_DSP_COST = {
    AtomOp.MUL: 1,
    AtomOp.MAC: 1,
    AtomOp.MADD: 1,
    AtomOp.DSP_MUL: 1,
    AtomOp.DSP_MAC: 1,
}
FPGA_DSP_COST.update({k: 0 for k in FPGA_LUT_COST if k not in FPGA_DSP_COST})

# Flip-flops: one FF per bit per pipeline stage
# For 8-bit data, PIPE costs ~8 FF; DELAY costs depth×8 FF
FPGA_FF_COST = {
    AtomOp.PIPE: 8,
    AtomOp.DELAY: 8,          # per cycle of delay
    AtomOp.ACC_INIT: 8,
    AtomOp.ACC_STEP: 16,     # state + accumulator
    AtomOp.ACC_READ: 0,
    AtomOp.ACC_RESET: 0,
    AtomOp.BUFFER: 16,       # read + write pointers + FIFO
}
FPGA_FF_COST.update({k: 0 for k in FPGA_LUT_COST if k not in FPGA_FF_COST})

# BRAM blocks (used for buffers larger than shallow FIFOs)
FPGA_BRAM_COST = {
    AtomOp.BUFFER: 0.5,     # deep buffers may use BRAM
}
FPGA_BRAM_COST.update({k: 0 for k in FPGA_LUT_COST if k not in FPGA_BRAM_COST})

# Routing cost penalty — driven by fan-out
# A node with high fan-out is harder to place & route
def fpga_route_cost(node, fan_out: int = 1) -> float:
    """Routing penalty increases with fan-out (>4 → congestion)."""
    if node.op in (AtomOp.BROADCAST, AtomOp.ROUTE):
        return fan_out * 2.0   # explicit routing
    if fan_out <= 1:
        return 0
    if fan_out <= 4:
        return (fan_out - 1) * 0.3
    return (fan_out - 4) * 0.8 + 0.9  # congestion penalty

# Critical path delay (ns) — calibrated for Xilinx 7-series speed grade -2
# LUT delay ~0.5ns, DSP delay ~2.5ns, routing ~0.3-1.5ns
FPGA_DELAY_NS = {
    AtomOp.ADD: 0.8,           # LUT + short route
    AtomOp.MUL: 2.5,           # DSP48
    AtomOp.MAC: 2.8,           # DSP cascade
    AtomOp.MADD: 2.8,
    AtomOp.DSP_MUL: 2.5,
    AtomOp.DSP_MAC: 2.8,
    AtomOp.SHL: 0.3,           # wiring
    AtomOp.SHR: 0.3,
    AtomOp.SAT: 0.8,
    AtomOp.ROUND: 0.8,
    AtomOp.REDUCE_ADD: 0.8,
    AtomOp.REDUCE_MAX: 0.8,
    AtomOp.REDUCE_MIN: 0.8,
    AtomOp.SCAN: 1.5,
    AtomOp.PACK: 0,
    AtomOp.UNPACK: 0,
    AtomOp.CONCAT: 0,
    AtomOp.SLICE: 0,
    AtomOp.EXTRACT: 0,
    AtomOp.BUFFER: 0.3,        # FF delay only
    AtomOp.ROUTE: 1.2,         # long wire
    AtomOp.BROADCAST: 0.8,
    AtomOp.PIPE: 0.3,          # FF clock-to-Q + setup
    AtomOp.DELAY: 0.3,
    AtomOp.QUANT: 1.0,
    AtomOp.DEQUANT: 1.0,
    AtomOp.DEQUANT_W: 1.0,
    AtomOp.CONST: 0,
    AtomOp.VAR: 0,
    AtomOp.STR_LIT: 0,
    AtomOp.ZERO: 0,
    AtomOp.ONE: 0,
    AtomOp.ACC_INIT: 0.3,
    AtomOp.ACC_STEP: 1.0,
    AtomOp.ACC_READ: 0.3,
    AtomOp.ACC_RESET: 0.3,
}

# Max achievable frequency (MHz) for a given critical path depth
def max_freq_mhz(critical_path_ns: float) -> float:
    if critical_path_ns <= 0:
        return 500.0
    f = 1000.0 / critical_path_ns
    return min(f, 500.0)

# Initiation interval: cycles between accepting new inputs
# 0 = combinational (accepts new input every cycle)
# 1+ = pipelined (new input every N cycles)
FPGA_II = {
    AtomOp.PIPE: 1,         # register breaks path → allows overlap
    AtomOp.ADD: 0,          # combinational → can accept every cycle if pipelined
    AtomOp.MUL: 0,
    AtomOp.MAC: 0,
    AtomOp.DSP_MUL: 0,
    AtomOp.DSP_MAC: 0,
}
FPGA_II.update({k: 0 for k in FPGA_LUT_COST if k not in FPGA_II})

# Throughput (million results/second) = Fmax_MHz / max_pipeline_depth_II
def throughput_mrps(fmax_mhz: float, pipeline_depth: int) -> float:
    """Million results per second for a pipelined design.
    After initial fill (pipeline_depth cycles), outputs 1 result/cycle."""
    if pipeline_depth <= 0:
        return fmax_mhz  # combinational: 1 result per cycle at Fmax
    return fmax_mhz  # pipelined: 1 result per cycle after fill

def latency_cycles(pipeline_depth: int) -> int:
    """Total cycles from first input to first output."""
    return pipeline_depth

# Latency in cycles (for pipeline-aware extraction)
# PIPE adds 1 cycle, DELAY adds N cycles
FPGA_CYC_LATENCY = {
    AtomOp.PIPE: 1,
    AtomOp.DELAY: 1,           # per cycle (multiplied by depth)
    AtomOp.BUFFER: 2,          # FIFO read latency
}
FPGA_CYC_LATENCY.update({k: 0 for k in FPGA_LUT_COST if k not in FPGA_CYC_LATENCY})


# ── Backward-compatible aliases ──

OP_COST = {k: FPGA_LUT_COST.get(k, 0) + FPGA_DSP_COST.get(k, 0) * 3
           + FPGA_FF_COST.get(k, 0) * 0.1 for k in FPGA_LUT_COST}

OP_LATENCY = FPGA_DELAY_NS


# ── Combined FPGA cost: weighted sum ──

def fpga_cost_fn(node, fan_out: int = 1) -> float:
    """Single number: lower = better FPGA implementation."""
    lut  = FPGA_LUT_COST.get(node.op, 0)
    dsp  = FPGA_DSP_COST.get(node.op, 0) * 10    # DSPs are valuable
    ff   = FPGA_FF_COST.get(node.op, 0) * 0.05   # FF are abundant
    bram = FPGA_BRAM_COST.get(node.op, 0) * 20   # BRAM is scarce
    route = fpga_route_cost(node, fan_out)
    delay = FPGA_DELAY_NS.get(node.op, 0) * 2    # delay weight
    return lut + dsp + ff + bram + route + delay


# ── Datatypes ──

class DataType(Enum):
    UINT8 = auto(); INT4 = auto(); INT8 = auto(); INT16 = auto()
    INT32 = auto(); FP16 = auto(); FP32 = auto(); BOOL = auto()


@dataclass(frozen=True, order=True)
class ENode:
    op: AtomOp
    children: tuple      # e-class IDs
    meta: Any = None

    def __repr__(self):
        m = f"[{self.meta}]" if self.meta else ""
        return f"{self.op.name}({','.join(map(str, self.children))}){m}"


def op_arity(op: AtomOp) -> int:
    return {
        AtomOp.MUL: 2, AtomOp.ADD: 2, AtomOp.MAC: 3, AtomOp.MADD: 3,
        AtomOp.SHL: 2, AtomOp.SHR: 2, AtomOp.SAT: 3, AtomOp.ROUND: 2,
        AtomOp.REDUCE_ADD: 2, AtomOp.REDUCE_MAX: 2, AtomOp.REDUCE_MIN: 2,
        AtomOp.SCAN: 2,
        AtomOp.PACK: 2, AtomOp.UNPACK: 2, AtomOp.CONCAT: 2,
        AtomOp.SLICE: 3, AtomOp.EXTRACT: 3,
        AtomOp.BUFFER: 2, AtomOp.ROUTE: 3, AtomOp.BROADCAST: 2,
        AtomOp.PIPE: 1, AtomOp.DELAY: 2,
        AtomOp.DSP_MUL: 2, AtomOp.DSP_MAC: 3,
        AtomOp.QUANT: 3, AtomOp.DEQUANT: 3, AtomOp.DEQUANT_W: 3,
        AtomOp.CONST: 0, AtomOp.VAR: 1, AtomOp.STR_LIT: 0,
        AtomOp.ZERO: 0, AtomOp.ONE: 0,
        AtomOp.ACC_INIT: 1, AtomOp.ACC_STEP: 2, AtomOp.ACC_READ: 1, AtomOp.ACC_RESET: 1,
    }.get(op, 0)
