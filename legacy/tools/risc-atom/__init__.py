"""
RISC Atom Decomposer: convert hardware design tasks into atomic RISC operations.

Usage:
  python -m tools.risc-atom demo       # run demo
  python -m tools.risc-atom list       # list atoms
  python -m tools.risc-atom decompose --task pipeline --ops '[...]'
"""

from .cli import main

if __name__ == "__main__":
    main()
