#!/usr/bin/env python3
"""Plot every holdout instance, including infeasible baseline/search results."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from explore_report import best, points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--title', help='explicit experiment label; use post-hoc for reused cases')
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    if summary.get('status') != 'complete':
        raise ValueError('Complete experiment required')
    candidates = points(summary)
    shapes = {r['case']: (r['width'], len(r['coefficients'])) for r in summary['results']}
    strata = sorted(set(shapes.values()))
    mhz = summary['config']['frequency_mhz']
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none',
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots((len(strata)+1)//2, 2, figsize=(12, 10), squeeze=False)
    groups = [('basic', 'Direct baseline', '#98a2b3'), ('template', 'Template search', '#007f83'),
              ('egraph', 'E-graph search', '#9c4dcc')]
    for ax, shape in zip(axes.flat, strata):
        names = sorted(name for name, value in shapes.items() if value == shape)
        has_choice = False
        for j, (group, label, color) in enumerate(groups):
            for i, name in enumerate(names):
                choice = best([p for p in candidates if p['case'] == name], group, dsp=0, mhz=mhz)
                x = i + (j-1)*0.25
                if choice:
                    has_choice = True
                    ax.bar(x, choice['comb'], width=0.23, color=color, label=label if i == 0 else None)
                else:
                    ax.text(x, 0, 'N/A', rotation=90, ha='center', va='bottom', color=color, fontsize=8)
        ax.set_title(f'{shape[0]}-bit, {shape[1]} inputs', loc='left', fontweight='bold')
        ax.set_xticks(range(len(names)), [name.split('_')[1] if name.startswith('random') else name for name in names])
        ax.set_xlabel('Case / frozen sample index')
        ax.set_ylabel('TRELLIS_COMB elements')
        ax.set_xlim(-0.6, len(names)-0.4)
        ax.set_ylim(bottom=0)
        if not has_choice:
            ax.set_ylim(0, 1)
            ax.set_yticks([])
            ax.set_ylabel('')
            ax.text(0.5, 0.5, f'No candidate meets\n{mhz:g} MHz / 0 DSP', transform=ax.transAxes,
                    ha='center', va='center', fontsize=13, color='#555555')
        ax.set_axisbelow(True)
        ax.grid(axis='y', alpha=0.18)
    for ax in list(axes.flat)[len(strata):]:
        ax.set_visible(False)
    handles = [plt.Rectangle((0, 0), 1, 1, color=color) for _, _, color in groups]
    fig.legend(handles, [label for _, label, _ in groups], ncol=3, loc='upper center', bbox_to_anchor=(0.5, 0.95), frameon=False)
    fig.suptitle(args.title or f'Arbitrary-coefficient holdout: all {len(shapes)} instances', x=0.065, ha='left', fontsize=18, fontweight='bold')
    seeds = '/'.join(map(str, summary['config']['pnr_seeds']))
    fig.text(0.065, 0.018, f'0 DSP, worst-seed Fmax >= {mhz:g} MHz | latency={summary["config"]["latency"]}, II=1 | ECP5 LFE5U-25F-6 | nextpnr seeds {seeds}\n'
             'N/A: no proved candidate meets the timing constraint. FF tradeoffs are reported separately.\n'
             'Internal routed timing estimates; no board measurement. Coefficients and all resource tuples are in the report.',
             fontsize=9, color='#555555')
    fig.tight_layout(rect=(0, 0.09, 1, 0.91), h_pad=2)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out.with_suffix('.png'), dpi=160)
    svg = args.out.with_suffix('.svg')
    fig.savefig(svg)
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines()) + '\n')


if __name__ == '__main__':
    main()
