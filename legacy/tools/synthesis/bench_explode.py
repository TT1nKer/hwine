import sys, time
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES

# Remove carry_group if present, keep only basic Boolean rules
basic_rules = [(name, fn) for name, fn in RULES if name != 'carry_group']

for N in [4, 8, 16]:
    print(f"\n{'='*50}")
    print(f"{N}-bit adder with basic Boolean rules only")
    print(f"Rules: {[n for n,_ in basic_rules]}")
    print(f"{'='*50}")

    t0 = time.time()
    eg = EGraph()
    ensure_constants(eg)
    ins = {}
    for name in [f'a{i}' for i in range(N)] + [f'b{i}' for i in range(N)] + ['cin']:
        ins[name] = eg.make_class()
    carry = ins['cin']
    for i in range(N):
        a = ins[f'a{i}']
        b = ins[f'b{i}']
        g = eg.add(ENode(Op.AND, (a, b)))
        p = eg.add(ENode(Op.XOR, (a, b)))
        pc = eg.add(ENode(Op.AND, (p, carry)))
        carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))

    print(f"  Initial: {len(eg.classes)} classes")

    for it in range(10):
        before = len(eg.classes)
        for name, fn in basic_rules:
            fn(eg)
        eg.rebuild()
        eg.clear_changed()
        after = len(eg.classes)
        growth = after - before
        bar = '+' * min(growth // 10, 40) if growth > 0 else ''
        print(f"  it{it}: {before:>5} -> {after:>5}  (+{growth:>5}) {bar}")
        if after == before:
            print(f"  saturated at iteration {it}")
            break
        if after > 5000:
            print(f"  ABORT: exceeded 5000 classes")
            break

    t = time.time() - t0
    print(f"  time: {t:.2f}s, final: {len(eg.classes)} classes")
