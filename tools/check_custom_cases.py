#!/usr/bin/env python3
"""Exercise custom-case parsing, eliminated ports, and zero-latency cores."""
import argparse
import csv
from pathlib import Path
import explore

HEADER = 'case\twidth\tcoefficients\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'summary.json').unlink(missing_ok=True)

    def generate(text, folder, valid, balanced=False):
        manifest = out / (folder + '.tsv')
        manifest.write_text(text)
        target = out / folder
        command = ['cargo', 'run', '--locked', '--manifest-path', str(explore.ROOT / 'hwine-rs/Cargo.toml'),
                   '--example', 'explore_fixtures', '--', str(target), str(manifest)]
        if balanced:
            command.append('--balanced-digits')
        _, code, _ = explore.run(command, explore.ROOT, out / (folder + '.log'))
        assert (code == 0) == valid, folder
        if not valid:
            assert not target.exists(), 'Invalid input wrote partial output'
        return target

    rtl = generate(HEADER + 'zero_mixed\t8\t0,127,-128\nidentity\t8\t0,1\n'
                   'sym_extreme\t12\t-2048,2047,2047,-2048\n'
                   'wide\t16\t32767,-32768,0,-1\nminimum\t2\t0,-2,1\n', 'valid', True, balanced=True)
    invalid = [
        '', HEADER, 'bad\theader\n', HEADER + '../escape\t8\t1,2\n',
        HEADER + 'duplicate\t8\t1,2\nduplicate\t8\t3,4\n',
        HEADER + 'x\t1\t0,1\n', HEADER + 'x\t17\t1,2\n',
        HEADER + 'x\t8\t128,1\n', HEADER + 'x\t8\t-129,1\n',
        HEADER + 'x\t8\t0,0\n', HEADER + 'x\t8\t1\n',
        HEADER + 'x\t8\t1,2,3,4,5,6,7,8,9\n', HEADER + 'x\t8\t1,no\n',
        HEADER + 'x\t8\t1,2\textra\n',
    ]
    for i, text in enumerate(invalid):
        generate(text, f'invalid-{i}', False)
    selected = [
        'zero_mixed_csd_balanced_p0', 'zero_mixed_egraph_dsp_p0',
        'identity_egraph_delay_p1', 'sym_extreme_csd_symmetry_p2',
        'wide_mixed_1_p0', 'minimum_csd_balanced_p0',
        'zero_mixed_csd_digits_balanced_p0', 'sym_extreme_csd_digits_balanced_p2',
    ]
    records = []
    for case in csv.DictReader((rtl / 'manifest.tsv').open(), delimiter='\t'):
        if case['name'] not in selected:
            continue
        case['width'], case['core_latency'] = int(case['width']), int(case['core_latency'])
        case['coefficients'] = list(map(int, case['coefficients'].split(',')))
        work = out / case['name']
        work.mkdir(exist_ok=True)
        (work / 'kernel.sv').write_bytes((rtl / (case['name'] + '.sv')).read_bytes())
        (work / 'source.sv').write_bytes((rtl / (case['name'] + '_source.sv')).read_bytes())
        (work / 'top.sv').write_text(explore.wrapper(case))
        source = explore.linear_formal(case, work)
        simulation = explore.simulate(case, work)
        proof = explore.formal(case, work, True, 45)
        assert proof['status'] == 'proved', case['name']
        records.append({'case': case, 'source': source, 'simulation': simulation, 'pipeline': proof})
    assert len(records) == len(selected)
    # A hand-written leaf independently exercises the shell's zero-core-stage
    # contract; the current extractor need not simplify its generated identity.
    case = {'name': 'independent_leaf', 'width': 8, 'coefficients': [0, 1], 'core_latency': 0}
    work = out / case['name']
    work.mkdir(exist_ok=True)
    for module, filename in [('kernel', 'kernel.sv'), ('source', 'source.sv')]:
        (work / filename).write_text(f'module {module}(input signed [7:0] a0, w0, output [7:0] result); assign result=w0; endmodule\n')
    (work / 'top.sv').write_text(explore.wrapper(case))
    source = explore.linear_formal(case, work)
    simulation = explore.simulate(case, work)
    proof = explore.formal(case, work, True, 45)
    assert proof['status'] == 'proved'
    records.append({'case': case, 'source': source, 'simulation': simulation, 'pipeline': proof})
    explore.dump(out / 'summary.json', {'status': 'passed', 'invalid_inputs_rejected': len(invalid),
                                      'verified_cases': records})
    print(f'PASS: {len(invalid)} invalid manifests rejected; {len(records)} custom cases simulated and proved')


if __name__ == '__main__':
    main()
