import sys
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES, rule
from tools.synthesis.extract import extract_optimal

@rule("carry_group")
def carry_group(eg):
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    for cid, node in matches:
        g1, and_cid = node.children
        and_cls = eg.find(and_cid)
        if and_cls not in eg.classes: continue
        for an in list(eg.classes[and_cls].nodes):
            if an.op != Op.AND or len(an.children) != 2: continue
            p1, cin_cid = an.children
            cin_cls = eg.find(cin_cid)
            if cin_cls not in eg.classes: continue
            for cn in list(eg.classes[cin_cls].nodes):
                if cn.op != Op.OR or len(cn.children) != 2: continue
                g0, a0_cid = cn.children
                a0_cls = eg.find(a0_cid)
                if a0_cls not in eg.classes: continue
                for a0n in list(eg.classes[a0_cls].nodes):
                    if a0n.op != Op.AND or len(a0n.children) != 2: continue
                    p0, cin = a0n.children
                    t1 = eg.add(ENode(Op.AND, (p1, g0)))
                    G = eg.add(ENode(Op.OR, (g1, eg.find(t1))))
                    P = eg.add(ENode(Op.AND, (p1, p0)))
                    t2 = eg.add(ENode(Op.AND, (eg.find(P), cin)))
                    nc = eg.add(ENode(Op.OR, (eg.find(G), eg.find(t2))))
                    if nc >= 0 and nc != eg.find(cid):
                        eg.union(eg.find(cid), nc)

def count_carry_levels(eg, cid, visited=None):
    """Count how many carry-combine levels in the optimal path."""
    if visited is None: visited = set()
    cid = eg.find(cid)
    if cid in visited: return 0, 'input'
    if cid not in eg.classes: return 0, 'input'
    visited.add(cid)
    ecls = eg.classes[cid]
    if not ecls.nodes: return 0, 'input'

    # Find the best (shallowest) node
    best_d, best_n = float('inf'), None
    for n in ecls.nodes:
        d = {Op.AND: 1.5, Op.OR: 1.5, Op.XOR: 2.5}.get(n.op, 1)
        mc = 0
        for child in n.children:
            cd, _ = count_carry_levels(eg, child, visited.copy())
            mc = max(mc, cd)
        if mc + d < best_d:
            best_d = mc + d
            best_n = n

    if best_n.op == Op.OR:
        # Check if this is a GP-combine OR node: OR(g, AND(p, cin))
        # Count the AND(p, cin) part as one carry level
        and_child = best_n.children[1]  # typically AND(p, cin) is child[1]
        ac = eg.find(and_child)
        if ac in eg.classes:
            for an in eg.classes[ac].nodes:
                if an.op == Op.AND:
                    # This OR node represents one carry-combine level
                    return 1, f'OR(carry_level)'
        return 0, 'OR(other)'
    return 0, str(best_n.op)

N = 32
eg = EGraph()
ensure_constants(eg)
ins = {}
for name in [f'a{i}' for i in range(N)] + [f'b{i}' for i in range(N)] + ['cin']:
    ins[name] = eg.make_class()
carry = ins['cin']
outputs = {}
for i in range(N):
    a = ins[f'a{i}']; b = ins[f'b{i}']
    g = eg.add(ENode(Op.AND, (a, b)))
    p = eg.add(ENode(Op.XOR, (a, b)))
    pc = eg.add(ENode(Op.AND, (p, carry)))
    carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))
outputs['cout'] = eg.find(carry)

for it in range(4):
    for _, fn in RULES: fn(eg)
    eg.rebuild(); eg.clear_changed()

# Extract optimal and inspect the cout node choice
opt = extract_optimal(eg, outputs, 'opt', max_depth=500)

# Find what the extractor picked for cout
cout_cid = eg.find(outputs['cout'])
ecls = eg.classes[cout_cid]

# Show all implementations with their rough depth (OR-count based)
def or_count(eg, cid, visited=None):
    if visited is None: visited = set()
    cid = eg.find(cid)
    if cid in visited or cid not in eg.classes: return 0
    visited.add(cid)
    best = float('inf')
    for n in eg.classes[cid].nodes:
        if n.op == Op.OR:
            d = 1
        elif n.op == Op.AND:
            d = 0.5
        else:
            d = 0.7
        mc = 0
        for ch in n.children:
            mc = max(mc, or_count(eg, ch, visited.copy()))
        best = min(best, mc + d)
    return best if best < float('inf') else 0

print("cout implementations ranked by depth (lower = faster):")
ranked = []
for i, n in enumerate(list(ecls.nodes)):
    d = or_count(eg, eg.find(cout_cid), set())
    ranked.append((d, n))
    if i < 10 or d < 20:  # show top 6
        pass

ranked.sort()
prev = None
for d, n in ranked[:6]:
    short = str(n)
    if short != prev:
        label = ""
        if d < 8: label = "≈ Kogge-Stone (fastest, more area)"
        elif d < 15: label = "≈ Han-Carlson (balanced)"
        elif d < 25: label = "≈ Brent-Kung (area efficient)"
        else: label = "≈ ripple (baseline)"
        print(f"  depth={d:.1f} {label}")
        print(f"    {short[:120]}")
    prev = short

print(f"\nTotal: {len(ecls.nodes)} implementations")
print(f"Extractor picked: depth={opt.depth():.1f}")
print(f"Theoretical: ripple=96.0, Brent-Kung≈30, Han-Carlson≈22, Kogge-Stone≈18")
