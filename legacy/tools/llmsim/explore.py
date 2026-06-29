"""
Parameter space explorer for LinearInt4 implementations.
Searches tile sizes, lanes, and layout options.
Ranks by constraints: area, bandwidth, latency.
"""

from .model import LinearSpec, ImplConfig, MemorySpec, cost_summary
from typing import Optional


TILE_K_VALUES = [32, 64, 128, 256, 512]
TILE_O_VALUES = [8, 16, 32, 64, 128, 256]
LANES_VALUES  = [8, 16, 32, 64, 128]


def explore(spec: LinearSpec,
            max_sram_kb: Optional[float] = None,
            max_cycles: Optional[int] = None,
            max_bw_gbps: Optional[float] = None,
            mem: Optional[MemorySpec] = None,
            sort_by: str = "cycles",
            top_n: int = 5) -> list[dict]:
    """
    Enumerate all valid implementation configs for a layer spec.
    Filter by constraints, sort by metric, return top N.
    """
    results = []

    for tk in TILE_K_VALUES:
        if tk > spec.K:
            continue
        for to_ in TILE_O_VALUES:
            if to_ > spec.O:
                continue
            for lanes in LANES_VALUES:
                if lanes > tk:
                    continue
                if tk % lanes != 0:
                    continue

                cfg = ImplConfig(tile_k=tk, tile_o=to_, lanes=lanes)
                cost = cost_summary(cfg, spec, mem)

                # Apply constraints
                if max_sram_kb and cost["sram_KB"] > max_sram_kb:
                    continue
                if max_cycles and cost["cycles"] > max_cycles:
                    continue
                if max_bw_gbps and cost["bw_GBps_at_10tok"] > max_bw_gbps:
                    continue

                results.append(cost)

    # Sort
    if sort_by == "cycles":
        results.sort(key=lambda r: r["cycles"])
    elif sort_by == "sram_KB":
        results.sort(key=lambda r: r["sram_KB"])
    elif sort_by == "bw_GBps_at_10tok":
        results.sort(key=lambda r: r["bw_GBps_at_10tok"])

    return results[:top_n]


def pareto_front(spec: LinearSpec, mem: Optional[MemorySpec] = None) -> list[dict]:
    """Find Pareto-optimal configs minimizing cycles AND SRAM."""
    all_results = []

    for tk in TILE_K_VALUES:
        if tk > spec.K:
            continue
        for to_ in TILE_O_VALUES:
            if to_ > spec.O:
                continue
            for lanes in LANES_VALUES:
                if lanes > tk or tk % lanes != 0:
                    continue
                cfg = ImplConfig(tile_k=tk, tile_o=to_, lanes=lanes)
                cost = cost_summary(cfg, spec, mem)
                all_results.append(cost)

    # Pareto filter: nondominated in (cycles, sram_KB)
    pareto = []
    for r in all_results:
        dominated = False
        for other in all_results:
            if (other["cycles"] <= r["cycles"] and
                other["sram_KB"] <= r["sram_KB"] and
                (other["cycles"] < r["cycles"] or
                 other["sram_KB"] < r["sram_KB"])):
                dominated = True
                break
        if not dominated:
            pareto.append(r)

    pareto.sort(key=lambda r: r["cycles"])
    return pareto
