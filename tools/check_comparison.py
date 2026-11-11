#!/usr/bin/env python3
"""Small independent negative controls for candidate-extension comparisons."""
from copy import deepcopy

from compare_candidate_extension import pair_records, validate_policy
from compare_explorations import normalized_netlist


def rejected(action, marker):
    try:
        action()
    except AssertionError as exc:
        assert marker in str(exc), str(exc)
    else:
        raise AssertionError(f'Invalid comparison accepted: {marker}')


def main():
    if not __debug__:
        raise RuntimeError('Controls require assertions; do not use -O')
    config = {'latency': 4, 'pnr_seeds': [1, 2, 3], 'frequency_mhz': 150,
              'scope_filter': '', 'case_manifest': {'sha256': 'manifest'},
              'tools': {'yosys': 'same-version', 'experiment_driver_sha256': 'before'},
              'source_sha256': {'core.rs': 'unchanged', 'tools/explore.py': 'before'}}
    extended = deepcopy(config)
    extended.update(candidate_options={'balanced_digits': True}, generator={'fingerprint': 'new'})
    extended['tools']['experiment_driver_sha256'] = 'after'
    extended['source_sha256']['tools/explore.py'] = 'after'
    assert validate_policy(config, extended) == {'tools/explore.py': {'baseline': 'before', 'expanded': 'after'}}
    for key, value in [('latency', 6), ('pnr_seeds', [1, 2, 4]), ('frequency_mhz', 200),
                       ('case_manifest', {'sha256': 'different'})]:
        bad = deepcopy(extended)
        bad[key] = value
        rejected(lambda: validate_policy(config, bad), 'Measurement policies differ')
    bad = deepcopy(extended)
    bad['source_sha256']['core.rs'] = 'changed'
    rejected(lambda: validate_policy(config, bad), 'Core/checker source changed')
    bad = deepcopy(extended)
    bad['tools']['yosys'] = 'new-version'
    rejected(lambda: validate_policy(config, bad), 'Measurement policies differ')

    record = {'case': 'example', 'rtl_sha256': 'common', 'status': 'proved',
              'aliases': [{'name': 'original', 'group': 'template', 'core_latency': 3}],
              'measurements': [{'mapping': 'nodsp', 'worst_fmax_mhz': 140,
                                'routes': [{'seed': 1, 'fmax_mhz': 140}, {'seed': 2, 'fmax_mhz': 150}]}]}
    base = {'results': [record]}
    new = {'results': [deepcopy(record)]}
    new['results'][0]['aliases'].append({'name': 'new-alias', 'group': 'template', 'core_latency': 3})
    added = deepcopy(record)
    added['rtl_sha256'] = 'added'
    added['aliases'] = [{'name': 'added-candidate', 'group': 'template', 'core_latency': 2}]
    new['results'].append(added)
    pairs, extra = pair_records(base, new)
    assert len(pairs) == 1 and extra == [('example', 'added')]
    bad = deepcopy(new)
    bad['results'][0]['measurements'][0]['routes'][1]['fmax_mhz'] = 149  # same worst seed
    rejected(lambda: pair_records(base, bad), 'Measured results or proof records differ')
    bad = deepcopy(new)
    bad['results'][0]['status'] = 'unproved-timeout'
    rejected(lambda: pair_records(base, bad), 'Measured results or proof records differ')
    bad = deepcopy(new)
    bad['results'][0]['aliases'][0]['group'] = 'egraph'
    rejected(lambda: pair_records(base, bad), 'Alias metadata differs')
    bad = deepcopy(new)
    bad['results'] = bad['results'][1:]
    rejected(lambda: pair_records(base, bad), 'Baseline implementations missing')
    bad = deepcopy(new)
    bad['results'].append(deepcopy(bad['results'][0]))
    rejected(lambda: pair_records(base, bad), 'Duplicate case/RTL record')
    bad = deepcopy(new)
    other = deepcopy(added)
    other['case'] = 'other-case'
    bad['results'].append(other)
    rejected(lambda: pair_records(base, bad), 'Case sets differ')
    assert len(pair_records(base, bad, 'example')[0]) == 1
    rejected(lambda: pair_records(base, bad, 'absent'), 'No records in requested scope')

    left = {'attributes': {'src': '/local/eda/cells.v:10'}, 'type': 'ADD',
            'parameters': {'WIDTH': 16}, 'connections': {'A': [1, 2]},
            'other': '/local/eda/cells.v:10'}
    right = deepcopy(left)
    right['attributes']['src'] = '/remote/eda/cells.v:10'
    canonical = normalized_netlist(left, '/local/eda')
    assert canonical == normalized_netlist(right, '/remote/eda')
    for mutate in [lambda x: x.update(type='SUB'),
                   lambda x: x['parameters'].update(WIDTH=8),
                   lambda x: x['connections'].update(A=[2, 1]),
                   lambda x: x['attributes'].update(src='/remote/eda/cells.v:11'),
                   lambda x: x.update(other='/remote/eda/cells.v:10')]:
        bad = deepcopy(right)
        mutate(bad)
        assert canonical != normalized_netlist(bad, '/remote/eda')
    print('PASS: extension comparison accepts added coverage; rejects policy, source, '
          'per-seed timing, proof, alias, coverage, and structural changes')


if __name__ == '__main__':
    main()
