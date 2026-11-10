#!/usr/bin/env python3
"""Frozen, outcome-independent coefficient sample for the second experiment."""
import argparse
from pathlib import Path
import random

SEED = 0x484F4C444F555432


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    rng = random.Random(SEED)
    lines = ['case\twidth\tcoefficients']
    for width in [8, 12, 16]:
        for terms in [3, 6]:
            for sample in range(4):
                coefficients = [rng.randrange(-(1 << (width-1)), 1 << (width-1)) for _ in range(terms)]
                # No coefficient screening, symmetry injection, or rejection
                # based on synthesis, verification, timing, or search results.
                assert any(coefficients)
                name = f'random{terms}_{sample}_s{width}'
                lines.append(f'{name}\t{width}\t' + ','.join(map(str, coefficients)))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    main()
