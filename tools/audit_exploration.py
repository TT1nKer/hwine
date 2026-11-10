#!/usr/bin/env python3
"""Check experiment records against retained RTL, certificates, and tool reports.

This is an evidence-consistency audit, not a replacement for the proof engines
or a post-synthesis equivalence check. It does not rerun placement/routing.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import subprocess
import linear_check

ROOT = Path(__file__).resolve().parents[1]


def audit(summary, root, check_current_sources=False, source_commit=None):
    if not __debug__:
        raise RuntimeError('Evidence audit requires Python assertions; do not use -O')
    assert summary['status'] == 'complete', 'Incomplete experiment'
    config = summary['config']
    hashes = {}

    def sha(path):
        stat = path.stat()
        key = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns)
        if key not in hashes:
            hashes[key] = hashlib.sha256(path.read_bytes()).hexdigest()
        return hashes[key]

    assert sha(ROOT / 'tools/linear_check.py') == config['source_sha256']['tools/linear_check.py'], 'Checker version mismatch'
    if check_current_sources:
        for name, expected in config['source_sha256'].items():
            assert sha(ROOT / name) == expected, name
    if source_commit:
        source_commit = subprocess.check_output(
            ['git', 'rev-parse', '--verify', '--end-of-options', source_commit + '^{commit}'], cwd=ROOT, text=True).strip()
        for name, expected in config['source_sha256'].items():
            data = subprocess.check_output(['git', 'show', f'{source_commit}:{name}'], cwd=ROOT)
            assert hashlib.sha256(data).hexdigest() == expected, name
    if config.get('case_manifest'):
        assert sha(root / 'cases.tsv') == config['case_manifest']['sha256'], 'Case snapshot changed'
        cases = {c['case']: c for c in csv.DictReader((root / 'cases.tsv').open(), delimiter='\t')}
        selected = {name for name in cases if config['scope_filter'] in name}
        assert {r['case'] for r in summary['results']} == selected, 'Missing/extra cases'
        for result in summary['results']:
            case = cases[result['case']]
            assert result['width'] == int(case['width'])
            assert result['coefficients'] == list(map(int, case['coefficients'].split(',')))
    manifest = {c['name']: c for c in csv.DictReader((root / 'rtl/manifest.tsv').open(), delimiter='\t')
                if config['scope_filter'] in c['case']}
    assert {a['name'] for r in summary['results'] for a in r['aliases']} == set(manifest), 'Missing/extra variants'
    sources, syntheses, routes = set(), set(), set()
    comparisons, proved, timeouts = 0, 0, 0
    for result in summary['results']:
        verification = root / result['verification']['artifact']
        source = root / result['source_proof']['artifact']
        actual = hashlib.sha256((verification / 'kernel.sv').read_bytes() +
                                (verification / 'top.sv').read_bytes()).hexdigest()
        assert actual == result['rtl_sha256'], 'RTL hash mismatch'
        assert sha(verification / 'source.sv') == sha(source / 'source.sv'), 'Proof composition mismatch'
        for alias in result['aliases']:
            fixture = manifest[alias['name']]
            assert fixture['case'] == result['case'] and int(fixture['width']) == result['width']
            assert list(map(int, fixture['coefficients'].split(','))) == result['coefficients']
            for key in ['style', 'group', 'interval', 'core_latency', 'estimated_delay']:
                assert str(alias[key]) == fixture[key], 'Alias metadata mismatch'
            assert sha(root / 'rtl' / (alias['name'] + '.sv')) == sha(verification / 'kernel.sv')
        if result['status'] == 'proved':
            assert result['verification']['formal']['status'] == 'proved'
            for name in ['formal-base.log', 'formal-induction.log']:
                assert 'Status: PASSED' in (verification / name).read_text(), name
            assert len(result['measurements']) == 2
            proved += 1
        else:
            assert result['status'] == 'unproved-timeout' and not result['measurements']
            assert result['verification']['formal']['status'] == 'timeout'
            log = (verification / 'formal.log').read_text().lower()
            assert 'timeout' in log or 'timed out' in log
            timeouts += 1
        count = int(re.search(r'SIM_PASS checked=(\d+)', (verification / 'simulation.log').read_text())[1])
        assert count == result['verification']['simulation']['comparisons']
        comparisons += count
        width, coefficients = result['width'], result['coefficients']
        mask = (1 << width) - 1
        vectors = (verification / 'vectors.hex').read_text().splitlines()
        assert len(vectors) - 3 <= count <= len(vectors)
        for vector in vectors:
            packed = int(vector, 16)
            expected, packed = packed & mask, packed >> width
            value = 0
            for coefficient in reversed(coefficients):
                x, packed = packed & mask, packed >> width
                signed = x - (1 << width) if x & (1 << (width - 1)) else x
                value += signed * coefficient
            assert packed == 0 and value & mask == expected, 'Simulation oracle mismatch'
        if source not in sources:
            certificate = json.loads((source / 'certificate.json').read_text())
            assert result['source_proof']['status'] == 'proved'
            assert certificate['rtl_sha256'] == sha(source / 'source.sv')
            assert certificate['netlist_sha256'] == sha(source / 'source.json')
            checked = json.loads(json.dumps(linear_check.check(json.loads((source / 'source.json').read_text()),
                                                               width, coefficients)))
            assert all(certificate[k] == v for k, v in checked.items()), 'Certificate mismatch'
            sources.add(source)
        for mapping in result['measurements']:
            synthesis = root / mapping['synthesis']['artifact']
            netlist_sha = sha(synthesis / 'netlist.json')
            assert netlist_sha == mapping['synthesis']['netlist_sha256']
            for filename in ['kernel.sv', 'top.sv']:
                assert sha(synthesis / filename) == sha(verification / filename)
            stat = json.loads((synthesis / 'stat.json').read_text())
            assert stat['design']['num_cells_by_type'] == mapping['synthesis']['cells']
            syntheses.add(synthesis)
            assert [r['seed'] for r in mapping['routes']] == config['pnr_seeds']
            for route in mapping['routes']:
                folder = root / route['artifact']
                assert sha(folder / 'netlist.json') == netlist_sha
                timing = json.loads((folder / 'timing.json').read_text())
                assert len(timing['fmax']) == 1
                assert next(iter(timing['fmax'].values()))['achieved'] == route['fmax_mhz']
                assert timing['utilization'] == route['utilization']
                assert 'Program finished normally.' in (folder / 'pnr.log').read_text()
                routes.add(folder)
            assert min(r['fmax_mhz'] for r in mapping['routes']) == mapping['worst_fmax_mhz']
    return {'status': 'passed', 'current_source_hashes_checked': check_current_sources,
            'source_commit_checked': source_commit,
            'rtl_records': len(summary['results']), 'proved': proved, 'timeouts': timeouts,
            'simulation_comparisons': comparisons, 'source_certificates_rechecked': len(sources),
            'synthesis_records': len(syntheses), 'routing_records': len(routes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument('--check-current-sources', action='store_true')
    sources.add_argument('--source-commit', help='check historical source hashes against this Git commit')
    args = parser.parse_args()
    result = audit(json.loads(args.summary.read_text()), args.summary.parent, args.check_current_sources, args.source_commit)
    result['summary_sha256'] = hashlib.sha256(args.summary.read_bytes()).hexdigest()
    result['audit_script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
