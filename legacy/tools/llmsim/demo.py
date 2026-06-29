"""
Demo: LLM linear layer exploration with different memory options.
Shows how compute-bound vs memory-bound trade-off changes with memory tech.
"""

from .model import LinearSpec, ImplConfig, MemorySpec, MEMORY_OPTIONS, cost_summary
from .explore import explore


def main():
    up_layer = LinearSpec("W_up", K=4096, O=11008)

    print("=" * 70)
    print("Memory Technology Impact on Llama-2-7B FFN (int4)")
    print("=" * 70)
    print(f"\n  Weight:   {up_layer.weight_bytes()/1e6:.1f} MB per layer")
    print(f"  MACs:     {up_layer.macs()/1e6:.0f}M per token")
    print(f"  Compute cycles (ideal BW): {explore(up_layer, mem=None, sort_by='cycles', top_n=1)[0]['cycles']:,}")

    # Config: 128 lanes, fully tiled
    cfg = ImplConfig(tile_k=128, tile_o=128, lanes=128)

    print(f"\n{'Memory':<20s} {'BW GB/s':>8s} {'Cycles':>10s} {'Tok/s@500MHz':>12s} {'Bottleneck':>12s} {'Cost':>6s}")
    print("-" * 70)

    for key in ["ddr4_1ch", "ddr4_2ch", "ddr5_2ch", "lpddr5_4ch", "gddr6_8ch", "hbm2e_8ch", "hbm3_16ch", None]:
        mem = MEMORY_OPTIONS.get(key) if key else None
        bw_str = f"{mem.total_bw_gbps:.0f}" if mem else "∞"
        cost_str = f"{mem.cost_factor:.1f}x" if mem else "—"

        cost = cost_summary(cfg, up_layer, mem)
        cycles = cost["cycles"]
        tok_s = 500e6 / cycles if cycles > 0 else float('inf')

        print(f"{mem.name if mem else 'ideal (compute-bound)':<20s} "
              f"{bw_str:>8s} "
              f"{cycles:>10,} "
              f"{tok_s:>12.1f} "
              f"{cost['governor']:>12s} "
              f"{cost_str:>6s}")

    # Practical comparison: best home-viable options
    print(f"\n{'='*70}")
    print("Practical tier breakdown")
    print(f"{'='*70}")
    tiers = [
        ("Budget (DDR4 2ch)", "ddr4_2ch"),
        ("Mid-range (DDR5 2ch)", "ddr5_2ch"),
        ("Enthusiast (LPDDR5 4ch)", "lpddr5_4ch"),
        ("Workstation (GDDR6)", "gddr6_8ch"),
        ("Datacenter (HBM2e)", "hbm2e_8ch"),
    ]
    for name, key in tiers:
        mem = MEMORY_OPTIONS[key]
        cost = cost_summary(cfg, up_layer, mem)
        tok_s = 500e6 / cost["cycles"]
        print(f"  {name:<25s}: {tok_s:>6.0f} tok/s @ 500MHz, {mem.total_bw_gbps:.0f} GB/s, {mem.cost_factor:.1f}x DDR4")


if __name__ == "__main__":
    main()
