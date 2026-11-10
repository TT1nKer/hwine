#!/usr/bin/env python3
"""Non-vacuity checks for the experiment's independent oracle and cycle contract."""
import argparse
import csv
import json
from pathlib import Path
import explore


def rejected(action, marker, log=None):
    try:
        action()
    except RuntimeError as exc:
        evidence = log.read_text() if log else str(exc)
        if marker not in evidence:
            raise
    else:
        raise AssertionError('Negative control was incorrectly accepted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rtl-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    case = {'width': 8, 'coefficients': [7, 13, -5], 'core_latency': 1}
    name = 'dot3_s8_direct_left_p0'
    core = (args.rtl_dir / (name + '.sv')).read_text()
    source = (args.rtl_dir / (name + '_source.sv')).read_text()
    top = explore.wrapper(case)
    controls = []
    manifest = list(csv.DictReader((args.rtl_dir / 'manifest.tsv').open(), delimiter='\t'))
    for positive in ['dot3_s8_direct_left_p0', 'dot3_s8_egraph_delay_p2']:
        c = next(r for r in manifest if r['name'] == positive)
        c['width'], c['core_latency'] = int(c['width']), int(c['core_latency'])
        c['coefficients'] = list(map(int, c['coefficients'].split(',')))
        work = args.out / positive
        work.mkdir(exist_ok=True)
        (work / 'kernel.sv').write_text((args.rtl_dir / (positive + '.sv')).read_text())
        (work / 'source.sv').write_text((args.rtl_dir / (positive + '_source.sv')).read_text())
        (work / 'top.sv').write_text(explore.wrapper(c))
        proof = explore.linear_formal(c, work)
        simulation = explore.simulate(c, work)
        sequential = explore.formal(c, work, True, 20)
        if sequential['status'] != 'proved':
            raise AssertionError('Positive pipeline was not proved')
        controls.append({'positive': positive, 'source': proof, 'simulation': simulation, 'formal': sequential})
    for mutation in ['oracle', 'latency', 'reset']:
        work = args.out / mutation
        work.mkdir(exist_ok=True)
        c, k, t = case.copy(), core, top
        if mutation == 'oracle':
            c['coefficients'] = [6, 13, -5]
        elif mutation == 'latency':
            assert 'assign result = pad1;' in t
            t = t.replace('assign result = pad1;', 'assign result = pad0;')
        else:
            k = k.replace('if (!rst_n)', "if (1'b0)")
            t = t.replace('if (!rst_n)', "if (1'b0)")
        (work / 'kernel.sv').write_text(k)
        (work / 'top.sv').write_text(t)
        (work / 'source.sv').write_text(source)
        rejected(lambda: explore.simulate(c, work), 'MISMATCH')
        marker = 'proof did fail' if mutation == 'oracle' else 'Status: FAILED'
        rejected(lambda: explore.formal(c, work, mutation != 'oracle', 20), marker, work / 'formal.log')
        controls.append({'mutation': mutation, 'simulation': 'rejected', 'formal': 'rejected'})
    (args.out / 'summary.json').write_text(json.dumps(controls, indent=2) + '\n')
    print('PASS: two correct pipelines accepted; wrong oracle, latency, and reset rejected by simulation and formal')


if __name__ == '__main__':
    main()
