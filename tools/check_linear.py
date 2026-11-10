#!/usr/bin/env python3
"""Cross-check restricted algebra certificates against SAT and rejection cases."""
import argparse
from pathlib import Path
import explore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    valid = [
        ('native', "a0 * 4'd7 + w0 * 4'd13", [7, 13]),
        ('distribute', "(a0 + w0) * 4'd7", [7, 7]),
        ('csd', "(a0 << 8'd3) - a0 + w0", [7, 1]),
        ('negative', "a0 * 4'hb + w0", [-5, 1]),
        ('offset_cancels', "(a0 + 4'd3) * 4'd7 - 4'd5 + w0", [7, 1]),
        ('overshift', "(a0 << 64'd64) + w0", [0, 1]),
        ('cancel', 'a0 - a0 + w0 - w0', [0, 0]),
    ]
    invalid = [
        ('nonlinear', '', 'a0 * w0'),
        ('right_shift', '', "(a0 >>> 8'd1) + w0"),
        ('variable_shift', '', 'a0 << w0'),
        ('partial_wiring', '', '{a0[2:0], a0[3]}'),
        ('truncation', 'wire [2:0] q = a0 + w0;', 'q'),
        ('unknown', '', "4'bx001"),
        ('mux', '', "a0[0] ? a0 : w0"),
    ]
    results = []
    for name, expr, coeff in valid:
        work = args.out / name
        work.mkdir(parents=True, exist_ok=True)
        (work / 'source.sv').write_text(
            f'module source(input signed [3:0] a0, w0, output [3:0] result); assign result = {expr}; endmodule\n')
        case = {'width': 4, 'coefficients': coeff}
        proof = explore.linear_formal(case, work)
        sat = explore.formal(case, work, False, 20)
        if sat['status'] != 'proved':
            raise AssertionError(f'SAT did not corroborate {name}')
        try:
            explore.linear_formal({**case, 'coefficients': [coeff[0] + 1, coeff[1]]}, work)
        except ValueError as exc:
            if 'LINEAR_MISMATCH' not in str(exc):
                raise
        else:
            raise AssertionError('Wrong coefficient accepted')
        results.append({'case': name, 'linear': proof['status'], 'sat': sat['status'], 'wrong_coefficient': 'rejected'})
    for name, declarations, expr in invalid:
        work = args.out / name
        work.mkdir(parents=True, exist_ok=True)
        (work / 'source.sv').write_text(
            f'module source(input signed [3:0] a0, w0, output [3:0] result); {declarations} assign result = {expr}; endmodule\n')
        try:
            explore.linear_formal({'width': 4, 'coefficients': [1, 1]}, work)
        except ValueError as exc:
            if 'LINEAR_MISMATCH' in str(exc):
                raise AssertionError('Unsupported structure was evaluated instead of rejected') from exc
            results.append({'case': name, 'status': 'rejected', 'reason': str(exc)})
        else:
            raise AssertionError(f'Unsupported structure accepted: {name}')
    explore.dump(args.out / 'summary.json', results)
    print(f'PASS: {len(valid)} algebra/SAT cross-checks, {len(valid)} wrong coefficients, {len(invalid)} unsupported structures')


if __name__ == '__main__':
    main()
