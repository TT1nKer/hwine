#!/usr/bin/env python3
"""Standalone scientific plot of the bounded ECP5 experiment (matplotlib)."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from explore_report import best, belongs, points


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('summary', type=Path)
    p.add_argument('--out', type=Path, required=True, help='output filename stem')
    args = p.parse_args()
    summary = json.loads(args.summary.read_text())
    if summary.get('status') != 'complete':
        raise ValueError('Complete experiment required')
    ps = points(summary)
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False,
                         'svg.fonttype': 'none', 'figure.facecolor': 'white'})
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 5.3), gridspec_kw={'width_ratios': [1.25, 1]})
    groups = [('basic', 'Direct / symmetry', '#98a2b3'), ('template', 'Template search', '#007f83'),
              ('egraph', 'E-graph search', '#9c4dcc')]
    names = ['dot3', 'dot4', 'sym4', 'sym6', 'sum4', 'sum8']
    for j, (group, label, color) in enumerate(groups):
        for i, family in enumerate(names):
            choice = best([x for x in ps if x['case'] == family + '_s16'], group, dsp=0, mhz=150)
            x = i + (j-1)*0.25
            if choice:
                axes[0].bar(x, choice['comb'], width=0.23, color=color, label=label if i == 0 else None)
            else:
                axes[0].text(x, 3, 'N/A', rotation=90, ha='center', va='bottom', color=color, fontsize=8)
    axes[0].set_xticks(range(len(names)), names)
    axes[0].set_ylabel('TRELLIS_COMB elements (lower is better)')
    axes[0].set_title('16-bit kernels: 0 DSP, worst-seed Fmax >= 150 MHz', loc='left', fontsize=11)
    axes[0].legend(frameon=False, loc='upper right')
    axes[0].grid(axis='y', alpha=0.18)
    axes[0].set_axisbelow(True)
    seen = set()
    for x in ps:
        if x['case'] != 'dot3_s16':
            continue
        key = (x['comb'], x['ff'], x['dsp'], x['fmax_mhz'], x['rtl_sha256'])
        if key in seen:
            continue
        seen.add(key)
        group = 'egraph' if belongs(x, 'egraph') and not belongs(x, 'template') else 'template'
        color = dict((g, c) for g, _, c in groups)[group]
        axes[1].scatter(x['comb'], x['fmax_mhz'], color=color, marker='o' if x['dsp'] == 0 else '^',
                        s=40, alpha=0.75, edgecolors='white', linewidths=0.4)
    axes[1].axhline(150, color='#666666', linestyle='--', linewidth=1)
    axes[1].set_xlabel('TRELLIS_COMB elements (lower is better)')
    axes[1].set_ylabel('Worst of 3 routed Fmax estimates (MHz)')
    axes[1].set_title('16-bit dot3: measured resource / timing tradeoff', loc='left', fontsize=11)
    axes[1].grid(alpha=0.18)
    for marker, label in [('o', '0 DSP'), ('^', 'Uses DSP')]:
        axes[1].scatter([], [], color='#555555', marker=marker, label=label)
    axes[1].legend(frameon=False, loc='upper right')
    fig.suptitle('Verified FPGA design-space pilot', x=0.065, y=0.99, ha='left', fontsize=17, fontweight='bold')
    fig.text(0.065, 0.025, 'LFE5U-25F-6 | II=1, latency=4 | nextpnr seeds 1/2/3 | internal timing estimates, not board Fmax\n'
             'Cell minimization can increase flip-flops; complete resource tuples and all 18 instances are in the report.',
             fontsize=9, color='#555555')
    fig.tight_layout(rect=(0, 0.10, 1, 0.94))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for suffix in ['.png', '.svg']:
        fig.savefig(args.out.with_suffix(suffix), dpi=160)


if __name__ == '__main__':
    main()
