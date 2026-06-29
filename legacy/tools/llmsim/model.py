"""
LinearInt4 Implementation Model.

Models a 4-bit weight streaming matrix-vector multiplication:
    y[O] = W[O,K] · x[K]   (int4 weights, int8 activations)

Parameters define the spatial implementation:
  - tile_k: K-dimension tile size (how much of x is active at once)
  - tile_o: O-dimension tile size (how many outputs computed in parallel)
  - lanes: number of MAC units working in parallel per output
  - weight_layout: how packed int4 weights are stored in memory
  - sram_kb: on-chip SRAM budget for activation buffer + weight buffer
"""

from dataclasses import dataclass
from typing import Optional
import math


@dataclass(frozen=True)
class MemorySpec:
    """Memory technology specification."""
    name: str
    bw_per_ch_gbps: float   # bandwidth per channel (GB/s)
    channels: int = 1
    width_bits: int = 64
    cost_factor: float = 1.0   # relative to DDR4

    @property
    def total_bw_gbps(self) -> float:
        return self.bw_per_ch_gbps * self.channels


# Available memory technologies
MEMORY_OPTIONS = {
    "ddr4_1ch":      MemorySpec("DDR4-3200 1ch",     25.6, 1, 64, 1.0),
    "ddr4_2ch":      MemorySpec("DDR4-3200 2ch",     25.6, 2, 128, 1.1),
    "ddr5_2ch":      MemorySpec("DDR5-5600 2ch",     44.8, 2, 128, 1.3),
    "lpddr5_4ch":    MemorySpec("LPDDR5-6400 4ch",   51.2, 4, 64,  1.5),
    "gddr6_8ch":     MemorySpec("GDDR6 8ch",         112,  8, 32,  2.0),
    "hbm2e_8ch":     MemorySpec("HBM2e 8ch",         410,  8, 1024,5.0),
    "hbm3_16ch":     MemorySpec("HBM3 16ch",         819, 16, 1024,8.0),
}


@dataclass(frozen=True)
class LinearSpec:
    """Abstract specification: what to compute."""
    name: str
    K: int       # input dimension
    O: int       # output dimension
    w_bits: int = 4
    a_bits: int = 8
    group_size: int = 64   # quantization group size (for scales)

    def weight_bytes(self) -> float:
        raw = self.O * self.K * self.w_bits
        n_groups = math.ceil(self.K / self.group_size)
        scale = n_groups * self.O * 16
        return (raw + scale) / 8

    def macs(self) -> int:
        return self.O * self.K


@dataclass(frozen=True)
class ImplConfig:
    """One hardware implementation plan."""
    tile_k: int       # K tile size (32-512)
    tile_o: int       # O tile size (8-256)
    lanes: int        # parallel MACs per output channel
    weight_packed: bool = True  # pack 2 int4 per byte
    sram_kb: int = 256         # assumed SRAM
    acc_width: int = 32         # accumulator bit width
    pipeline_stages: int = 2
    fuse_gate_up: bool = False  # for FFN: process W_up and W_gate together

    def __post_init__(self):
        # Validate
        assert self.tile_k % self.lanes == 0, f"tile_k ({self.tile_k}) must be multiple of lanes ({self.lanes})"
        assert self.tile_k >= 32
        assert self.tile_o >= 8

    def cycles_per_output_tile(self) -> int:
        """MAC cycles to compute one O tile."""
        # Each MAC processes one (weight, activation) pair per cycle
        # With 'lanes' MACs, we need ceil(tile_k / lanes) cycles per output
        return math.ceil(self.tile_k / self.lanes)

    def num_o_tiles(self, spec: LinearSpec) -> int:
        return math.ceil(spec.O / self.tile_o)

    def num_k_tiles(self, spec: LinearSpec) -> int:
        return math.ceil(spec.K / self.tile_k)

    def total_cycles(self, spec: LinearSpec,
                      mem: Optional[MemorySpec] = None,
                      freq_mhz: int = 500) -> int:
        """Total cycles for one matrix-vector multiply.
        If mem is provided, accounts for DRAM bandwidth limit.
        If not, assumes compute-bound (ideal memory)."""
        o_tiles = self.num_o_tiles(spec)
        k_tiles = self.num_k_tiles(spec)
        cycles_per_ot = self.cycles_per_output_tile()
        compute_cycles = o_tiles * k_tiles * cycles_per_ot + self.pipeline_stages

        if mem is None:
            return compute_cycles

        # Memory bottleneck: time to stream all weights
        total_wbytes = spec.weight_bytes()
        bytes_per_cycle = mem.total_bw_gbps * 1e9 / (freq_mhz * 1e6)
        memory_cycles = math.ceil(total_wbytes / max(bytes_per_cycle, 0.1))
        return max(compute_cycles, memory_cycles)

    def weight_bytes(self, spec: LinearSpec) -> float:
        """Total weight memory footprint (bytes)."""
        raw_bits = spec.O * spec.K * spec.w_bits
        scale_bits = math.ceil(spec.K / spec.group_size) * spec.O * 16  # fp16 scales
        return (raw_bits + scale_bits) / 8

    def weight_bytes_per_token(self, spec: LinearSpec) -> float:
        """Weight bytes streamed per token (same as total since every weight is read once)."""
        return spec.weight_bytes()

    def bandwidth_required(self, spec: LinearSpec, target_tps: float) -> float:
        """Memory bandwidth needed (GB/s) for target tokens/sec."""
        bytes_per_tok = spec.weight_bytes()
        return bytes_per_tok * target_tps / 1e9

    def macs(self, spec: LinearSpec) -> int:
        """Total MAC operations per token."""
        return spec.O * spec.K

    def sram_used(self, spec: LinearSpec) -> int:
        """On-chip SRAM usage (bytes)."""
        w_bytes_per_elem = spec.w_bits / 8  # 0.5 for int4
        a_bytes_per_elem = spec.a_bits / 8  # 1 for int8
        # Activation buffer: tile_k × a_bytes_per_elem
        act_buf = math.ceil(self.tile_k * a_bytes_per_elem)
        # Weight buffer: tile_o × tile_k × w_bytes_per_elem
        wgt_buf = math.ceil(self.tile_o * self.tile_k * w_bytes_per_elem)
        # Accumulator buffer: tile_o × (acc_width/8)
        acc_buf = math.ceil(self.tile_o * (self.acc_width / 8))
        return act_buf + wgt_buf + acc_buf

    def sram_used_kb(self, spec: LinearSpec) -> float:
        return self.sram_used(spec) / 1024


    def hw_luts(self) -> int:
        """Estimated LUT count calibrated from Yosys synthesis (dot_int4_tile).
        Baseline: LANES=128, TILE_O=32 → 40,318 cells ≈ 40K LUT-equivalents.
        Model: ~300 LUTs per int4×int8 MAC lane + adder tree contribution."""
        return self.lanes * 300 + self.tile_o * 50 + 200

    def hw_ffs(self) -> int:
        """Estimated FF count: accumulators + result registers.
        Baseline: LANES=128, TILE_O=32, ACC_WIDTH=32 → 2,052 FFs.
        Model: 2 × TILE_O × ACC_WIDTH (acc + result) + FSM overhead."""
        return self.tile_o * self.acc_width * 2 + 10

    def hw_dsps(self) -> int:
        """Estimated DSP count (FPGA). Each int4×int8 can fit in LUTs;
        DSP count is primarily for larger multipliers or when lanes exceed LUT budget."""
        return 0


def cost_summary(cfg: ImplConfig, spec: LinearSpec,
                 mem: Optional[MemorySpec] = None) -> dict:
    """Generate cost summary for a configuration."""
    return {
        "config": cfg,
        "cycles": cfg.total_cycles(spec, mem),
        "weight_MB": spec.weight_bytes() / 1e6,
        "weight_per_tok_MB": cfg.weight_bytes_per_token(spec) / 1e6,
        "bw_req_at_10tok": cfg.bandwidth_required(spec, 10),
        "macs_M": spec.macs() / 1e6,
        "sram_KB": cfg.sram_used_kb(spec),
        "hw_luts": cfg.hw_luts(),
        "hw_ffs": cfg.hw_ffs(),
        "hw_dsps": cfg.hw_dsps(),
        "governor": _bottleneck(cfg, spec, mem),
    }


def _bottleneck(cfg: ImplConfig, spec: LinearSpec,
                mem: Optional[MemorySpec] = None) -> str:
    """Identify the bottleneck: compute or memory."""
    if mem is None:
        return "compute"
    compute_cyc = cfg.total_cycles(spec, None)
    mem_cyc = cfg.total_cycles(spec, mem)
    if mem_cyc > compute_cyc * 1.1:
        return "memory"
    elif compute_cyc > mem_cyc * 1.1:
        return "compute"
    return "balanced"
