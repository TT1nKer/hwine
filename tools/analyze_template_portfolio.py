#!/usr/bin/env python3
"""Post-hoc screen of small template portfolios; no new physical measurements.

Audit the input experiment separately. This fits on already inspected cases;
leave-one-case-out is an internal diagnostic, not an independent holdout.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from explore_report import best, compact, points


def analyze(summary):
    if summary.get('status') != 'complete':
        raise ValueError('A complete experiment is required; audit it separately')
    candidates = points(summary)
    cases = sorted({r['case'] for r in summary['results']})
    policies = sorted({(a['style'], a['interval'], p['mapping'])
                       for p in candidates for a in p['aliases']
                       if a['group'] == 'template'})
    lookup = {}
    for case in cases:
        for policy in policies:
            choices = [p for p in candidates
                       if p['case'] == case and p['mapping'] == policy[2]
                       and any(a['group'] == 'template'
                               and (a['style'], a['interval']) == policy[:2]
                               for a in p['aliases'])]
            lookup[case, policy] = best(choices, dsp=0, mhz=150)
    oracle = {c: best([p for p in candidates if p['case'] == c],
                      group='template', dsp=0, mhz=150) for c in cases}

    def choose(case, labels):
        return best([lookup[case, label] for label in labels
                     if lookup[case, label] is not None], dsp=0, mhz=150)

    def score(training_cases, labels):
        selected = {c: choose(c, labels) for c in training_cases}
        solved = [c for c in training_cases if selected[c]]
        return (-len(solved),
                sum(selected[c]['comb'] / oracle[c]['comb'] for c in solved),
                sum(selected[c]['ff'] for c in solved))

    def fit(training_cases, budget):
        chosen = []
        for _ in range(budget):
            policy = min((p for p in policies if p not in chosen),
                         key=lambda p: (score(training_cases, chosen + [p]), p))
            chosen.append(policy)
        return chosen

    def summarize(selected):
        solved = [c for c, p in selected.items() if p]
        gaps = [100 * (selected[c]['comb'] / oracle[c]['comb'] - 1) for c in solved]
        return {
            'feasible': len(solved), 'cases': len(cases),
            'oracle_feasible': sum(p is not None for p in oracle.values()),
            'same_comb_as_template_oracle': sum(selected[c]['comb'] == oracle[c]['comb'] for c in solved),
            'comb_gap_percent_paired_feasible_mean': statistics.mean(gaps) if gaps else None,
            'comb_gap_percent_paired_feasible_median': statistics.median(gaps) if gaps else None,
            'comb_gap_percent_paired_feasible_max': max(gaps) if gaps else None,
            'missed_oracle_feasible': [c for c in cases if oracle[c] is not None and selected[c] is None],
        }

    results = []
    for budget in [1, 2, 3, 4]:
        fixed = fit(cases, budget)
        held_out_choices, fold_labels = {}, []
        for held in cases:
            chosen = fit([c for c in cases if c != held], budget)
            fold_labels.append(tuple(chosen))
            held_out_choices[held] = choose(held, chosen)
        results.append({
            'budget_template_mapping_pairs': budget,
            'all_data_selected_fixed_portfolio': fixed,
            'in_sample_fixed_portfolio': summarize({c: choose(c, fixed) for c in cases}),
            'leave_one_case_out': summarize(held_out_choices),
            'leave_one_case_out_portfolios': [
                {'count': n, 'policies': p} for p, n in Counter(fold_labels).most_common()],
        })
    fixed = fit(cases, 2)
    selected = {c: choose(c, fixed) for c in cases}
    combined = {c: best([p for p in candidates if p['case'] == c], dsp=0, mhz=150) for c in cases}
    paired = [c for c in cases if selected[c] is not None and combined[c] is not None]
    gaps = [100 * (selected[c]['comb'] / combined[c]['comb'] - 1) for c in paired]
    return {
        'status': 'post-hoc-diagnostic', 'new_physical_runs': 0,
        'constraints': {'latency': summary['config']['latency'], 'dsp': 0,
                        'min_mhz': 150, 'pnr_seeds': summary['config']['pnr_seeds']},
        'policy': ('template style + pipeline interval + synthesis mapping; greedy maximize training '
                   'feasibility then minimize normalized combinational cost, then FF; lexicographic ties'),
        'limits': ('Same already inspected 24-case corpus; leave-one-case-out is exploratory internal '
                   'validation, not a new independent holdout or strong external-tool comparison. '
                   'Missing/infeasible candidates count as failure. Multiple policy aliases may share physical evidence.'),
        'results': results,
        'two_templates_vs_template_and_egraph_search': {
            'paired_feasible_cases': len(paired),
            'same_comb': sum(selected[c]['comb'] == combined[c]['comb'] for c in paired),
            'mean_comb_overhead_percent': statistics.mean(gaps) if gaps else None,
            'median_comb_overhead_percent': statistics.median(gaps) if gaps else None,
            'max_comb_overhead_percent': max(gaps) if gaps else None,
            'missed_combined_feasible': [c for c in cases if combined[c] is not None and selected[c] is None],
            'per_case': [{'case': c, 'portfolio': compact(selected[c]),
                          'combined': compact(combined[c])} for c in cases],
        },
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    report = analyze(json.loads(args.summary.read_text()))
    report['summary_sha256'] = hashlib.sha256(args.summary.read_bytes()).hexdigest()
    report['analysis_source_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Wrote post-hoc diagnostic: {args.out}; no new physical runs')


if __name__ == '__main__':
    main()
