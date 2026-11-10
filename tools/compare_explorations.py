#!/usr/bin/env python3
"""Audit and compare two runs, allowing only timings and named EDA source roots.

This checks recorded evidence and netlist JSON, not compiler correctness or
post-synthesis equivalence. Original artifacts and hashes are never rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path

from audit_exploration import audit


def measured_content(value):
    if isinstance(value, dict):
        # Each original artifact and netlist hash is independently audited.
        # Netlist content is compared separately with explicit source roots.
        return {k: measured_content(v) for k, v in value.items()
                if k not in ('seconds', 'artifact', 'netlist_sha256')}
    if isinstance(value, list):
        return [measured_content(v) for v in value]
    return value


def normalized_netlist(value, eda_root, path=()):
    if isinstance(value, dict):
        return {k: normalized_netlist(v, eda_root, path + (k,)) for k, v in value.items()}
    if isinstance(value, list):
        return [normalized_netlist(v, eda_root, path + (i,)) for i, v in enumerate(value)]
    if isinstance(value, str) and path[-2:] == ('attributes', 'src'):
        return value.replace(eda_root.rstrip('/') + '/', '$OSS_CAD_SUITE/')
    return value


def compare(left, right, left_root, right_root, left_eda, right_eda):
    audits = [audit(left, left_root), audit(right, right_root)]
    assert left['config'] == right['config'], 'Experiment configurations differ'
    assert measured_content(left) == measured_content(right), 'Measured results or proof records differ'
    lfiles = {p.relative_to(left_root / 'rtl'): p for p in (left_root / 'rtl').rglob('*') if p.is_file()}
    rfiles = {p.relative_to(right_root / 'rtl'): p for p in (right_root / 'rtl').rglob('*') if p.is_file()}
    assert lfiles.keys() == rfiles.keys(), 'Generated fixture file sets differ'
    for name, path in lfiles.items():
        assert path.read_bytes() == rfiles[name].read_bytes(), f'Generated fixture differs: {name}'
    compared, raw_equal = 0, 0
    for lrecord, rrecord in zip(left['results'], right['results']):
        for lm, rm in zip(lrecord['measurements'], rrecord['measurements']):
            lp = left_root / lm['synthesis']['artifact'] / 'netlist.json'
            rp = right_root / rm['synthesis']['artifact'] / 'netlist.json'
            raw_equal += lp.read_bytes() == rp.read_bytes()
            assert normalized_netlist(json.loads(lp.read_text()), left_eda) == normalized_netlist(
                json.loads(rp.read_text()), right_eda), f'Netlist differs: {lrecord["rtl_sha256"]}/{lm["mapping"]}'
            compared += 1
    return {
        'status': 'passed', 'left_audit': audits[0], 'right_audit': audits[1],
        'configurations_identical': True, 'generated_files_byte_identical': len(lfiles),
        'proof_results_and_all_per_seed_resources_and_fmax_identical': True,
        'synthesis_netlists_compared': compared, 'raw_netlists_byte_identical': raw_equal,
        'netlists_identical_after_explicit_eda_source_prefix_normalization': True,
        'normalization': {'only_field': 'attributes.src', 'left_eda_root': left_eda,
                          'right_eda_root': right_eda, 'replacement': '$OSS_CAD_SUITE'},
        'excluded_from_summary_comparison': ['wall seconds', 'artifact paths', 'individually audited netlist hashes'],
    }


def main():
    if not __debug__:
        raise RuntimeError('Comparison requires assertions; do not use -O')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('left', type=Path)
    parser.add_argument('right', type=Path)
    parser.add_argument('--left-eda-root', required=True)
    parser.add_argument('--right-eda-root', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    left, right = [json.loads(p.read_text()) for p in [args.left, args.right]]
    result = compare(left, right, args.left.parent, args.right.parent, args.left_eda_root, args.right_eda_root)
    result['summary_sha256'] = {label: hashlib.sha256(path.read_bytes()).hexdigest()
                                for label, path in [('left', args.left), ('right', args.right)]}
    result['comparison_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
