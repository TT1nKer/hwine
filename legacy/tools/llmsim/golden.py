"""
Golden reference models for DotInt4 and LinearInt4.
Every RTL implementation must match these bit-exact.

int4 range: [-8, 7]  (signed 4-bit)
int8 range: [-128, 127] (signed 8-bit)
Accumulator: int32
"""

import random
from dataclasses import dataclass
from typing import List, Tuple


# ---- Core operations ----

def dot_int4(w: List[int], x: List[int]) -> int:
    """Single dot product: sum(w[i] * x[i]) for i in range(K).
    w: int4 weights (values must be in [-8, 7])
    x: int8 activations (values must be in [-128, 127])
    Returns int32 accumulator.
    """
    acc = 0
    for wi, xi in zip(w, x):
        _check_int4(wi)
        _check_int8(xi)
        acc += wi * xi
    return acc


def linear_int4(W: List[List[int]], x: List[int]) -> List[int]:
    """Matrix-vector multiply: y[o] = sum_k W[o][k] * x[k].
    W: O × K int4 weight matrix
    x: length-K int8 activation vector
    Returns length-O int32 result vector.
    """
    O = len(W)
    if O == 0:
        return []
    K = len(W[0])
    assert len(x) == K, f"x length {len(x)} != W cols {K}"

    y = [0] * O
    for o in range(O):
        y[o] = dot_int4(W[o], x)
    return y


# ---- Tile-level (matching dot_int4_tile.sv interface) ----

@dataclass
class TileConfig:
    """Configuration matching dot_int4_tile parameters."""
    lanes: int = 128        # total MAC units
    tile_o: int = 32        # output channels per tile
    acc_width: int = 32

    @property
    def lanes_per_o(self) -> int:
        return self.lanes // self.tile_o

    def cycles_for_tile_k(self, tile_k: int) -> int:
        """Number of cycles needed to process tile_k input elements."""
        return (tile_k + self.lanes_per_o - 1) // self.lanes_per_o


def dot_tile_cycle(cfg: TileConfig,
                   a_slice: List[int],
                   w_slice: List[List[int]]) -> List[int]:
    """One cycle of dot_int4_tile: compute LANES_PER_O products per output channel.
    a_slice: LANES_PER_O activations (int8)
    w_slice: TILE_O × LANES_PER_O weights (int4), indexed as w_slice[o][l]
    Returns TILE_O partial sums for this cycle.
    """
    lp = cfg.lanes_per_o
    assert len(a_slice) == lp, f"activations: need {lp}, got {len(a_slice)}"
    assert len(w_slice) == cfg.tile_o
    for o in range(cfg.tile_o):
        assert len(w_slice[o]) == lp, f"w_slice[{o}]: need {lp}, got {len(w_slice[o])}"

    sums = [0] * cfg.tile_o
    for o in range(cfg.tile_o):
        for l in range(lp):
            sums[o] += w_slice[o][l] * a_slice[l]
    return sums


def dot_tile(cfg: TileConfig,
             a: List[int],
             W_tile: List[List[int]],
             tile_k: int) -> List[int]:
    """Full dot tile computation across tile_k input elements.
    a: length tile_k activation vector (int8)
    W_tile: TILE_O × tile_k weight matrix (int4)
    Returns TILE_O dot products (int32).
    """
    assert len(a) == tile_k
    assert len(W_tile) == cfg.tile_o
    for o in range(cfg.tile_o):
        assert len(W_tile[o]) == tile_k

    acc = [0] * cfg.tile_o
    cycles = cfg.cycles_for_tile_k(tile_k)
    lp = cfg.lanes_per_o

    for cyc in range(cycles):
        # Slice inputs for this cycle
        start = cyc * lp
        end = min(start + lp, tile_k)
        a_slice = _pad_or_trim(a[start:end], lp, 0)

        w_slice = []
        for o in range(cfg.tile_o):
            w_vals = _pad_or_trim(W_tile[o][start:end], lp, 0)
            w_slice.append(w_vals)

        cycle_sums = dot_tile_cycle(cfg, a_slice, w_slice)
        for o in range(cfg.tile_o):
            acc[o] += cycle_sums[o]

    return acc


# ---- Full LinearInt4 (tiling across both O and K) ----

@dataclass
class LinearInt4Plan:
    """Configuration for a full linear layer using dot_int4_tile."""
    cfg: TileConfig
    tile_k: int
    tile_o: int

    def num_k_tiles(self, K: int) -> int:
        return (K + self.tile_k - 1) // self.tile_k

    def num_o_tiles(self, O: int) -> int:
        return (O + self.tile_o - 1) // self.tile_o

    def compute(self, W: List[List[int]], x: List[int]) -> List[int]:
        """Full linear layer via tiled dot products.
        W: O × K int4 weight matrix
        x: length-K int8 activation vector
        Returns length-O int32 result.
        """
        O = len(W)
        K = len(W[0])
        assert len(x) == K

        y = [0] * O
        nk = self.num_k_tiles(K)
        no = self.num_o_tiles(O)

        for o_tile_idx in range(no):
            o_start = o_tile_idx * self.tile_o
            o_end = min(o_start + self.tile_o, O)
            n_active_o = o_end - o_start

            # Initialize accumulators for this O-tile
            tile_acc = [0] * n_active_o

            for k_tile_idx in range(nk):
                k_start = k_tile_idx * self.tile_k
                k_end = min(k_start + self.tile_k, K)
                tile_k = k_end - k_start

                # Extract activation slice
                a_slice = x[k_start:k_end]

                # Extract weight tile (pad to cfg.tile_o if partial)
                W_slice = []
                for o in range(o_start, o_end):
                    W_slice.append(W[o][k_start:k_end])

                # Pad to full tile dimensions
                W_slice = _pad_weights(W_slice, self.cfg.tile_o, tile_k, self.tile_k)

                # Compute this tile
                tile_result = dot_tile(self.cfg, a_slice, W_slice, self.tile_k)

                # Accumulate (only active outputs)
                for o_local in range(n_active_o):
                    tile_acc[o_local] += tile_result[o_local]

            # Write back
            for o_local in range(n_active_o):
                y[o_start + o_local] = tile_acc[o_local]

        return y


# ---- Random test data generators ----

def rand_int4() -> int:
    """Random int4 value in [-8, 7]."""
    return random.randint(-8, 7)


def rand_int8() -> int:
    """Random int8 value in [-128, 127]."""
    return random.randint(-128, 127)


def rand_weights(O: int, K: int) -> List[List[int]]:
    """Random O×K int4 weight matrix."""
    return [[rand_int4() for _ in range(K)] for _ in range(O)]


def rand_activations(K: int) -> List[int]:
    """Random length-K int8 activation vector."""
    return [rand_int8() for _ in range(K)]


# ---- Validation helpers ----

def _check_int4(v: int):
    assert -8 <= v <= 7, f"int4 overflow: {v}"


def _check_int8(v: int):
    assert -128 <= v <= 127, f"int8 overflow: {v}"


def _pad_or_trim(lst: List[int], n: int, pad: int) -> List[int]:
    """Pad or trim list to length n."""
    if len(lst) >= n:
        return lst[:n]
    return lst + [pad] * (n - len(lst))


def _pad_weights(W: List[List[int]], target_o: int, actual_k: int,
                 target_k: int) -> List[List[int]]:
    """Pad weights to full tile dimensions, zero-filling beyond actual K."""
    result = []
    for row in W:
        result.append(_pad_or_trim(row, target_k, 0))
    while len(result) < target_o:
        result.append([0] * target_k)
    return result
