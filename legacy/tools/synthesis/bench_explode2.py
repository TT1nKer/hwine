import sys, time
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES, rule

# --- Additional rules that would be needed to discover g/p ---

@rule("and_distrib")
def and_distrib(eg):
    """a & (b | c) = (a & b) | (a & c)"""
    matches = eg.ematch(lambda n: n.op == Op.AND and len(n.children) == 2)
    for cid, node in matches:
        a = node.children[0]
        or_cid = node.children[1]
        or_cls = eg.find(or_cid)
        if or_cls not in eg.classes: continue
        for inner in list(eg.classes[or_cls].nodes):
            if inner.op == Op.OR and len(inner.children) == 2:
                b, c = inner.children
                # (a & b) | (a & c)
                ab = eg.add(ENode(Op.AND, (a, b)))
                ac = eg.add(ENode(Op.AND, (a, c)))
                new_node = eg.add(ENode(Op.OR, (eg.find(ab), eg.find(ac))))
                target = eg.find(new_node)
                if target >= 0 and target != eg.find(cid):
                    eg.union(eg.find(cid), target)

@rule("or_into_xor")
def or_into_xor(eg):
    """a | b = (a ^ b) | (a & b) — key identity for g/p discovery"""
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    for cid, node in matches:
        a, b = node.children
        xor_ab = eg.add(ENode(Op.XOR, (a, b)))
        and_ab = eg.add(ENode(Op.AND, (a, b)))
        new_node = eg.add(ENode(Op.OR, (eg.find(xor_ab), eg.find(and_ab))))
        target = eg.find(new_node)
        if target >= 0 and target != eg.find(cid):
            eg.union(eg.find(cid), target)

# Remove carry_group if present
basic_rules = [(name, fn) for name, fn in RULES if name != 'carry_group']

MAX_CLASSES = 50000

for N in [4, 8, 16]:
    print(f"\n{'='*60}")
    print(f"{N}-bit adder: Boolean rules + distributivity + or_into_xor")
    print(f"{'='*60}")

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
    print(f"  {'it':>4} {'before':>7} {'after':>7} {'delta':>7} {'time':>8}")

    for it in range(30):
        before = len(eg.classes)
        t_it = time.time()

        # Apply all rules
        for name, fn in basic_rules + [('and_distrib', and_distrib), ('or_into_xor', or_into_xor)]:
            if name in ['and_distrib', 'or_into_xor'] or name != 'carry_group':
                fn(eg)

        eg.rebuild(); eg.clear_changed()
        after = len(eg.classes)
        delta = after - before
        dt = time.time() - t_it

        bar = '+' * min(abs(delta) // 2, 30) if delta != 0 else ''
        print(f"  {it:>4} {before:>7} {after:>7} {delta:+>7} {dt:>7.2f}s {bar}")

        if after == before:
            print(f"  → saturated")
            break
        if after > MAX_CLASSES:
            print(f"  → ABORT: exceeded {MAX_CLASSES} classes at iteration {it}")
            break

    t = time.time() - t0
    print(f"  Total: {len(eg.classes)} classes, {t:.1f}s")
