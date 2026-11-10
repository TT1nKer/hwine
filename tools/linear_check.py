#!/usr/bin/env python3
"""Exact checker for a deliberately restricted combinational RTL subset.

Consumes Yosys frontend JSON, NOT hwine IR. Every data operation must have
equal W-bit inputs/output. Add/subtract, multiplication by a constant, and
unsigned constant left shifts are linear maps over Z/(2**W). A certificate
records each net's coefficient vector (inputs followed by a constant term).
Anything outside this subset is rejected, including partial-vector wiring.

Trusted base: Yosys's Verilog frontend, Python arithmetic, and this checker.
This is a symbolic algebra check, not a SAT solver result or verified checker.
"""
import argparse
import json
from pathlib import Path


def check(netlist, width, coefficients, module='source'):
    if not 1 <= width <= 64:
        raise ValueError('Only widths 1..64 are supported')
    m = netlist['modules'][module]
    if m.get('memories') or m.get('processes'):
        raise ValueError('Sequential/memory constructs are unsupported')
    names = [f'a{i//2}' if i % 2 == 0 else f'w{i//2}' for i in range(len(coefficients))]
    if set(m['ports']) != set(names + ['result']):
        raise ValueError('Unexpected port set')
    modulus = 1 << width
    size = len(coefficients) + 1
    forms = {}
    driven = set()
    for i, name in enumerate(names):
        port = m['ports'][name]
        if port['direction'] != 'input' or len(port['bits']) != width:
            raise ValueError('Input must be a full-width vector')
        bits = tuple(port['bits'])
        if any(type(b) is not int for b in bits) or len(set(bits)) != width or driven.intersection(bits):
            raise ValueError('Aliased or malformed input ports')
        form = [0] * size
        form[i] = 1
        forms[bits] = form
        driven.update(bits)
    output = m['ports']['result']
    if output['direction'] != 'output' or len(output['bits']) != width:
        raise ValueError('Output must be a full-width vector')
    producers = {}
    for name, cell in m['cells'].items():
        if cell['type'] not in ('$add', '$sub', '$mul', '$shl'):
            raise ValueError(f'Unsupported cell {cell["type"]}')
        if set(cell['connections']) != {'A', 'B', 'Y'}:
            raise ValueError('Unexpected cell ports')
        if cell.get('port_directions') != {'A': 'input', 'B': 'input', 'Y': 'output'}:
            raise ValueError('Unexpected cell directions')
        p = {k: int(v, 2) for k, v in cell['parameters'].items()}
        if set(p) != {'A_WIDTH', 'B_WIDTH', 'Y_WIDTH', 'A_SIGNED', 'B_SIGNED'}:
            raise ValueError('Unexpected cell parameters')
        if any(p[k] not in (0, 1) for k in ('A_SIGNED', 'B_SIGNED')):
            raise ValueError('Invalid signedness')
        if p['A_WIDTH'] != width or p['Y_WIDTH'] != width:
            raise ValueError('Mixed-width arithmetic is unsupported')
        if cell['type'] == '$shl':
            if p['B_SIGNED'] or not 1 <= p['B_WIDTH'] <= 64:
                raise ValueError('Shift count must be unsigned, width 1..64')
        elif p['B_WIDTH'] != width:
            raise ValueError('Mixed-width arithmetic is unsupported')
        for port_name in ['A', 'B', 'Y']:
            if len(cell['connections'][port_name]) != p[port_name + '_WIDTH']:
                raise ValueError('Connection width mismatch')
        bits = tuple(cell['connections']['Y'])
        if any(type(b) is not int for b in bits) or len(set(bits)) != width or driven.intersection(bits):
            raise ValueError('Multiple or malformed drivers')
        driven.update(bits)
        producers[bits] = (name, cell)
    active = set()
    steps = []

    def literal(bits):
        if all(b in ('0', '1') for b in bits):
            return sum((b == '1') << i for i, b in enumerate(bits))
        return None

    def evaluate(bits):
        bits = tuple(bits)
        if len(bits) != width:
            raise ValueError('Partial data vector')
        constant = literal(bits)
        if constant is not None:
            return [0] * (size - 1) + [constant]
        if bits in forms:
            return forms[bits]
        if bits in active:
            raise ValueError('Combinational cycle')
        if bits not in producers:
            raise ValueError('Undriven, unknown, or partial-vector wiring')
        active.add(bits)
        name, cell = producers[bits]
        a = evaluate(cell['connections']['A'])
        if cell['type'] == '$shl':
            shift = literal(cell['connections']['B'])
            if shift is None:
                raise ValueError('Nonconstant shift count')
            factor = (1 << shift) if shift < width else 0
            form = [v * factor for v in a]
        else:
            b = evaluate(cell['connections']['B'])
            if cell['type'] == '$add':
                form = [x + y for x, y in zip(a, b)]
            elif cell['type'] == '$sub':
                form = [x - y for x, y in zip(a, b)]
            elif not any(a[:-1]):
                form = [a[-1] * y for y in b]
            elif not any(b[:-1]):
                form = [b[-1] * x for x in a]
            else:
                raise ValueError('Nonlinear multiplication')
        forms[bits] = [v % modulus for v in form]
        steps.append({'cell': name, 'op': cell['type'], 'output_bits': bits, 'coefficients': forms[bits]})
        active.remove(bits)
        return forms[bits]

    # Check dead cells too; hidden unsupported behavior is not silently ignored.
    for bits in producers:
        evaluate(bits)
    actual = evaluate(output['bits'])
    expected = [v % modulus for v in coefficients] + [0]
    if actual != expected:
        raise ValueError(f'LINEAR_MISMATCH: got {actual}, expected {expected}')
    return {'method': 'exact-modular-linear-normalization', 'status': 'proved',
            'width': width, 'modulus': modulus, 'inputs': names,
            'expected': expected, 'actual': actual, 'steps': steps}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('json', type=Path)
    parser.add_argument('--width', type=int, required=True)
    parser.add_argument('--coefficients', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    result = check(json.loads(args.json.read_text()), args.width, list(map(int, args.coefficients.split(','))))
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('LINEAR_PROOF_PASS')


if __name__ == '__main__':
    main()
