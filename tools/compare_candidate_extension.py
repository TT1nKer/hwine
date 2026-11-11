#!/usr/bin/env python3
"""Audit a balanced-digit extension and cross-check every retained baseline RTL.

Requires raw evidence from both runs. Differences in candidate coverage are
allowed; changes in the common implementations' measured outcomes are not.
This is an evidence comparison, not a new equivalence proof.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_exploration import audit
from compare_explorations import measured_content, normalized_netlist


def validate_policy(left, right, case=None):
    if not __debug__:
        raise RuntimeError('Comparison requires assertions; do not use -O')
    assert left.get('candidate_options', {'balanced_digits': False}) == {'balanced_digits': False}
    assert right.get('candidate_options') == {'balanced_digits': True}
    # These two files added templates and isolated generator builds. Core
    # rewriting, extraction, checker and dependencies must remain identical.
    ls, rs = left['source_sha256'], right['source_sha256']
    assert ls.keys() == rs.keys(), 'Tracked source file sets differ'
    changed = {k for k in ls if ls[k] != rs[k]}
    assert changed <= {'tools/explore.py', 'hwine-rs/examples/explore_fixtures.rs'}, 'Core/checker source changed'

    def measurement_policy(config):
        policy = {k: v for k, v in config.items()
                  if k not in ['candidate_options', 'generator', 'source_sha256']}
        policy['tools'] = {k: v for k, v in config['tools'].items() if k != 'experiment_driver_sha256'}
        if case is not None:
            policy.pop('scope_filter')
        return policy

    assert measurement_policy(left) == measurement_policy(right), 'Measurement policies differ'
    return {k: {'baseline': ls[k], 'expanded': rs[k]} for k in sorted(changed)}


def pair_records(left, right, case=None):
    def index(summary):
        records = [r for r in summary['results'] if case is None or r['case'] == case]
        indexed = {(r['case'], r['rtl_sha256']): r for r in records}
        assert len(records) == len(indexed), 'Duplicate case/RTL record'
        assert records, 'No records in requested scope'
        return indexed

    baseline, expanded = index(left), index(right)
    assert {k[0] for k in baseline} == {k[0] for k in expanded}, 'Case sets differ; specify --case for a one-case diagnostic'
    assert baseline.keys() <= expanded.keys(), 'Baseline implementations missing from extension'
    pairs = []
    for key, before in sorted(baseline.items()):
        after = expanded[key]
        la = {a['name']: a for a in before['aliases']}
        ra = {a['name']: a for a in after['aliases']}
        assert len(la) == len(before['aliases']) and len(ra) == len(after['aliases']), 'Duplicate alias'
        assert la.keys() <= ra.keys(), f'Baseline aliases missing: {key}'
        assert all(a == ra[name] for name, a in la.items()), f'Alias metadata differs: {key}'
        lr = measured_content({k: v for k, v in before.items() if k != 'aliases'})
        rr = measured_content({k: v for k, v in after.items() if k != 'aliases'})
        assert lr == rr, f'Measured results or proof records differ: {key}'
        pairs.append((before, after))
    return pairs, sorted(expanded.keys() - baseline.keys())


def compare(left, right, left_root, right_root, left_eda, right_eda, case=None):
    changed = validate_policy(left['config'], right['config'], case)
    audits = [audit(left, left_root), audit(right, right_root)]
    pairs, added = pair_records(left, right, case)
    fixtures, netlists, raw_equal, route_records = set(), 0, 0, 0
    for before, after in pairs:
        for alias in before['aliases']:
            for suffix in ['.sv', '_source.sv']:
                name = alias['name'] + suffix
                assert (left_root / 'rtl' / name).read_bytes() == (right_root / 'rtl' / name).read_bytes(), f'Fixture differs: {name}'
                fixtures.add(name)
        for lm, rm in zip(before['measurements'], after['measurements']):
            lp = left_root / lm['synthesis']['artifact'] / 'netlist.json'
            rp = right_root / rm['synthesis']['artifact'] / 'netlist.json'
            raw_equal += lp.read_bytes() == rp.read_bytes()
            assert normalized_netlist(json.loads(lp.read_text()), left_eda) == normalized_netlist(
                json.loads(rp.read_text()), right_eda), f'Netlist differs: {before["case"]}/{lm["mapping"]}'
            netlists += 1
            route_records += len(lm['routes'])
    return {
        'status': 'passed', 'scope': {'case': case, 'cases': sorted({a['case'] for a, _ in pairs})},
        'baseline_audit': audits[0], 'expanded_audit': audits[1],
        'measurement_policy_identical': True, 'changed_source_hashes': changed,
        'common_rtl': len(pairs), 'added_rtl': [{'case': c, 'rtl_sha256': h} for c, h in added],
        'baseline_alias_fixture_files_byte_identical': len(fixtures),
        'shared_proof_results_and_all_per_seed_resources_and_fmax_identical': True,
        'synthesis_netlists_compared': netlists, 'raw_netlists_byte_identical': raw_equal,
        'route_records_compared_including_cache_reuse': route_records,
        'netlists_identical_after_explicit_eda_source_prefix_normalization': True,
        'normalization': {'only_field': 'attributes.src', 'baseline_eda_root': left_eda,
                          'expanded_eda_root': right_eda, 'replacement': '$OSS_CAD_SUITE'},
        'excluded_from_record_comparison': ['wall seconds', 'artifact paths', 'individually audited netlist hashes'],
        'allowed_configuration_differences': ['balanced-digit candidate flag', 'generator build metadata',
                                             'listed generator/driver hashes', 'driver fingerprint',
                                             *(['explicit single-case scope filter'] if case else [])],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('baseline', type=Path)
    parser.add_argument('expanded', type=Path)
    parser.add_argument('--left-eda-root', required=True)
    parser.add_argument('--right-eda-root', required=True)
    parser.add_argument('--case', help='explicit diagnostic subset; omitted requires identical full case sets')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    left, right = [json.loads(p.read_text()) for p in [args.baseline, args.expanded]]
    result = compare(left, right, args.baseline.parent, args.expanded.parent,
                     args.left_eda_root, args.right_eda_root, args.case)
    result['summary_sha256'] = {label: hashlib.sha256(path.read_bytes()).hexdigest()
                                for label, path in [('baseline', args.baseline), ('expanded', args.expanded)]}
    result['comparison_source_sha256'] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                        for name in ['compare_candidate_extension.py', 'compare_explorations.py', 'audit_exploration.py']}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(f'PASS: {len(result["scope"]["cases"])} cases, {result["common_rtl"]} shared RTL, '
          f'{len(result["added_rtl"])} added RTL; full record: {args.out}')


if __name__ == '__main__':
    main()
