#!/usr/bin/env python3
"""Verify short/deep pipelines, reset, and rejection of wrong cycle contracts."""
import argparse
import csv
from pathlib import Path
import explore
from check_explore import rejected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').unlink(missing_ok=True)
    sample = next(r for r in csv.DictReader((explore.ROOT / 'experiments/holdout-v1.tsv').open(), delimiter='\t')
                  if r['case'] == 'random6_0_s16')
    manifest = out / 'case.tsv'
    manifest.write_text('case\twidth\tcoefficients\n' + '\t'.join(sample[k] for k in ['case', 'width', 'coefficients']) + '\n')
    records = []
    for latency in [2, 6, 8, 16]:
        work = out / f'latency-{latency}'
        work.mkdir(exist_ok=True)
        if latency in [2, 16]:
            case = {'width': 8, 'coefficients': [0, 1], 'core_latency': 0}
            for module, filename in [('kernel', 'kernel.sv'), ('source', 'source.sv')]:
                (work / filename).write_text(f'module {module}(input signed [7:0] a0, w0, output [7:0] result); assign result=w0; endmodule\n')
        else:
            rtl = work / 'rtl'
            explore.checked(['cargo', 'run', '--locked', '--manifest-path', str(explore.ROOT / 'hwine-rs/Cargo.toml'),
                             '--example', 'explore_fixtures', '--', str(rtl), str(manifest),
                             '--balanced-digits', '--latency', str(latency)], explore.ROOT, work / 'generation.log')
            cases = list(csv.DictReader((rtl / 'manifest.tsv').open(), delimiter='\t'))
            case = max(cases, key=lambda c: int(c['core_latency']))
            case['width'], case['core_latency'] = int(case['width']), int(case['core_latency'])
            case['coefficients'] = list(map(int, case['coefficients'].split(',')))
            assert 3 < case['core_latency'] < latency, 'Must exercise a formerly excluded deep core'
            for filename, suffix in [('kernel.sv', '.sv'), ('source.sv', '_source.sv')]:
                (work / filename).write_bytes((rtl / (case['name'] + suffix)).read_bytes())
        top = explore.wrapper(case, latency)
        (work / 'top.sv').write_text(top)
        source = explore.linear_formal(case, work)
        simulation = explore.simulate(case, work, latency)
        proof = explore.formal(case, work, True, 45, latency)
        assert proof['status'] == 'proved'
        records.append({'latency': latency, 'case': case, 'source': source,
                        'simulation': simulation, 'pipeline': proof})
        # The implementation remains unchanged; independent checkers must reject
        # a one-cycle-shorter specification, including the 16-stage boundary.
        negative = out / f'wrong-latency-{latency}'
        negative.mkdir(exist_ok=True)
        for filename in ['kernel.sv', 'source.sv', 'top.sv']:
            (negative / filename).write_bytes((work / filename).read_bytes())
        rejected(lambda: explore.simulate(case, negative, latency - 1), 'MISMATCH')
        rejected(lambda: explore.formal(case, negative, True, 45, latency - 1), 'Status: FAILED', negative / 'formal.log')
        records[-1]['wrong_latency_simulation_and_formal'] = 'rejected'
        if latency == 8:
            reset = out / 'wrong-reset-8'
            reset.mkdir(exist_ok=True)
            for filename in ['kernel.sv', 'top.sv', 'source.sv']:
                (reset / filename).write_text((work / filename).read_text().replace('if (!rst_n)', "if (1'b0)"))
            rejected(lambda: explore.simulate(case, reset, latency), 'MISMATCH')
            rejected(lambda: explore.formal(case, reset, True, 45, latency), 'Status: FAILED', reset / 'formal.log')
            records[-1]['wrong_reset_simulation_and_formal'] = 'rejected'
    try:
        explore.wrapper({'width': 8, 'coefficients': [1, 1], 'core_latency': 6}, 6)
    except ValueError:
        pass
    else:
        raise AssertionError('Overfull core accepted')
    explore.dump(out / 'summary.json', {'status': 'passed', 'verified_cases': records,
                                      'overfull_core_rejected': True})
    print('PASS: latencies 2/6/8/16, deep cores, wrong-cycle and reset controls')


if __name__ == '__main__':
    main()
