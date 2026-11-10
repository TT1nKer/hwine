#!/usr/bin/env python3
"""Summarize the measured ablation, or export a proven feasible implementation."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def points(summary):
    result = []
    for r in summary['results']:
        if r['status'] != 'proved':
            continue
        for m in r['measurements']:
            def used(resource):
                return max(x['utilization'][resource]['used'] for x in m['routes'])
            result.append({
                'case': r['case'], 'rtl_sha256': r['rtl_sha256'],
                'aliases': r['aliases'], 'mapping': m['mapping'],
                'comb': used('TRELLIS_COMB'), 'ff': used('TRELLIS_FF'),
                'dsp': used('MULT18X18D'), 'fmax_mhz': m['worst_fmax_mhz'],
                'seed_fmax_mhz': [x['fmax_mhz'] for x in m['routes']],
                'verification': r['verification']['artifact'],
                'source_proof': r['source_proof']['artifact'],
                'synthesis': m['synthesis']['artifact'],
                'routes': [x['artifact'] for x in m['routes']],
            })
    return result


def belongs(point, group):
    if group == 'all':
        return True
    if group == 'basic':
        return any(x['style'] in ('direct_balanced', 'direct_symmetry') for x in point['aliases'])
    return any(x['group'] == group for x in point['aliases'])


def best(choices, group='all', dsp=None, mhz=150, max_comb=None, max_ff=None):
    feasible = [p for p in choices if belongs(p, group) and p['fmax_mhz'] >= mhz
                and (dsp is None or p['dsp'] <= dsp)
                and (max_comb is None or p['comb'] <= max_comb)
                and (max_ff is None or p['ff'] <= max_ff)]
    # Objective is explicit: minimize combinational cells, then fabric FFs,
    # then DSPs, then use worst-seed timing as the final tiebreaker.
    return min(feasible, key=lambda p: (p['comb'], p['ff'], p['dsp'], -p['fmax_mhz'], p['rtl_sha256'])) if feasible else None


def resources(p):
    return (p['comb'], p['ff'], p['dsp']) if p else None


def compact(p):
    if p is None:
        return None
    return {k: p[k] for k in ['rtl_sha256', 'aliases', 'mapping', 'comb', 'ff', 'dsp', 'fmax_mhz', 'seed_fmax_mhz']}


def analyze(summary):
    candidates = points(summary)
    rows = []
    sensitivity = []
    frontier_additions = []
    for case in sorted({r['case'] for r in summary['results']}):
        cs = [p for p in candidates if p['case'] == case]
        feasible = [p for p in cs if p['fmax_mhz'] >= summary['config']['frequency_mhz']]
        templates = [p for p in feasible if belongs(p, 'template')]
        extra = {}
        for point in feasible:
            if not belongs(point, 'egraph'):
                continue
            # Covering equality also excludes an already available template.
            if any(all(t[k] <= point[k] for k in ['comb', 'ff', 'dsp']) for t in templates):
                continue
            if any(all(t[k] <= point[k] for k in ['comb', 'ff', 'dsp'])
                   and any(t[k] < point[k] for k in ['comb', 'ff', 'dsp']) for t in feasible):
                continue
            extra[resources(point)] = compact(point)
        frontier_additions.append({'case': case, 'min_mhz': summary['config']['frequency_mhz'],
                                   'egraph_additions': list(extra.values())})
        for mhz in sorted({100, summary['config']['frequency_mhz'], 200}):
            for dsp in [0, 1, 2, None]:
                choices = {g: best(cs, g, dsp, mhz)
                           for g in ['basic', 'template', 'egraph', 'all']}
                baseline, combined = choices['template'], choices['all']
                effect = 'no-feasible-design' if combined is None else 'same-resources'
                if combined is not None and baseline is None:
                    effect = 'newly-feasible'
                elif baseline is not None and resources(combined) < resources(baseline):
                    effect = 'fewer-resources'
                row = {'case': case, 'min_mhz': mhz, 'max_dsp': dsp, 'egraph_increment': effect,
                       **{g: compact(p) for g, p in choices.items()}}
                (rows if mhz == summary['config']['frequency_mhz'] else sensitivity).append(row)
    source_proofs = {r['source_proof']['artifact']: r['source_proof'] for r in summary['results']}
    routes = {route['artifact'] for r in summary['results'] for m in r['measurements'] for route in m['routes']}
    return {
        'config': summary['config'],
        'counts': {
            'cases': len({r['case'] for r in summary['results']}),
            'generated_variants': sum(len(r['aliases']) for r in summary['results']),
            'unique_rtl': len(summary['results']),
            'proven_rtl': sum(r['status'] == 'proved' for r in summary['results']),
            'simulation_comparisons': sum(r['verification']['simulation']['comparisons'] for r in summary['results']),
            'distinct_source_proofs': len(source_proofs),
            'source_proofs_passed': sum(p['status'] == 'proved' for p in source_proofs.values()),
            'sequential_proofs_passed': sum(r['verification']['formal']['status'] == 'proved' for r in summary['results']),
            'unique_routing_runs': len(routes),
        },
        'unproved': [{k: r[k] for k in ['case', 'aliases', 'source_proof', 'verification']}
                     for r in summary['results'] if r['status'] != 'proved'],
        'comparisons': rows,
        'frequency_sensitivity': sensitivity,
        'resource_frontier_additions': frontier_additions,
    }


def export_design(point, summary_path, summary, out):
    checker = Path(__file__).with_name('linear_check.py')
    if hashlib.sha256(checker.read_bytes()).hexdigest() != summary['config']['source_sha256']['tools/linear_check.py']:
        raise ValueError('Local linear checker differs from the recorded experiment')
    root = summary_path.parent
    verification = root / point['verification']
    rtl = (verification / 'kernel.sv').read_bytes() + (verification / 'top.sv').read_bytes()
    if hashlib.sha256(rtl).hexdigest() != point['rtl_sha256']:
        raise ValueError('Recorded RTL artifact has changed')
    # A nonempty destination is never silently overwritten.
    out.mkdir(parents=True, exist_ok=True)
    if any(out.iterdir()):
        raise ValueError(f'Export destination must be empty: {out}')
    for category in ['verification', 'source_proof', 'synthesis']:
        shutil.copytree(root / point[category], out / category)
    for i, path in enumerate(point['routes']):
        shutil.copytree(root / path, out / f'route-seed-{summary["config"]["pnr_seeds"][i]}')
    for filename in ['kernel.sv', 'top.sv']:
        shutil.copyfile(out / 'verification' / filename, out / filename)
    shutil.copyfile(checker, out / 'source_proof/linear_check.py')
    (out / 'selection.json').write_text(json.dumps({'config': summary['config'], 'selected': point}, indent=2) + '\n')
    (out / 'README.md').write_text(
        '# Measured arithmetic kernel\n\n'
        f"Case: `{point['case']}`. Top module: `dut` (`top.sv` + `kernel.sv`).\n\n"
        'Signed fixed-width wrapping result; independent input tuple each cycle. '
        'Synchronous active-low reset. Latency 4, initiation interval 1. '
        'No ready/valid, stalls, FIR sample history, saturation, or full-precision output.\n\n'
        f"ECP5 LFE5U-25F-6 CABGA381: {point['comb']} TRELLIS_COMB, "
        f"{point['ff']} fabric FF, {point['dsp']} DSP; worst routed estimate "
        f"{point['fmax_mhz']:.2f} MHz over seeds {summary['config']['pnr_seeds']}. "
        'IO locations are unconstrained. This is internal register-to-register '
        'timing from nextpnr, not a board measurement or IO timing guarantee.\n\n'
        'Reproduce proof/simulation by rerunning the commands at the top of '
        '`verification/*.log` from that directory. For the combinational proof, '
        'rerun `yosys -Q -T -s frontend.ys` in `source_proof`, then run the '
        'included `linear_check.py` on `source.json` with the width and '
        'coefficients recorded in `selection.json`/`certificate.json`. '
        'This restricted symbolic checker and the Yosys frontend are trusted; '
        'the checker itself is not formally verified. '
        'Each synthesis/routing directory also retains its command and inputs.\n'
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--out', type=Path)
    parser.add_argument('--case')
    parser.add_argument('--max-dsp', type=int)
    parser.add_argument('--min-mhz', type=float, default=150)
    parser.add_argument('--max-comb', type=int)
    parser.add_argument('--max-ff', type=int)
    parser.add_argument('--export', type=Path)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text())
    if summary.get('status') != 'complete':
        raise ValueError('A complete experiment summary is required')
    if args.case:
        selected = best([p for p in points(summary) if p['case'] == args.case], dsp=args.max_dsp,
                        mhz=args.min_mhz, max_comb=args.max_comb, max_ff=args.max_ff)
        if selected is None:
            raise SystemExit('No proven measured candidate satisfies these constraints.')
        if args.export:
            export_design(selected, args.summary.resolve(), summary, args.export.resolve())
        report = selected
    else:
        if args.export:
            raise ValueError('--export requires --case')
        report = analyze(summary)
    text = json.dumps(report, indent=2) + '\n'
    if args.out:
        args.out.write_text(text)
    else:
        print(text, end='')


if __name__ == '__main__':
    main()
