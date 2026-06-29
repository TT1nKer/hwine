import sys
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES, apply_all, rule

@rule("carry_group")
def carry_group(eg):
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    applied = 0
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
                        applied += 1
                    if applied >= 20: break
                if applied >= 20: break
            if applied >= 20: break
        if applied >= 20: break

def print_node(eg, node, indent=0):
    """Pretty print a node and its transitive children"""
    prefix = "  " * indent
    cid_str = str(node)[:80]
    print(f"{prefix}{cid_str}")
    for c in node.children:
        cc = eg.find(c)
        if cc in eg.classes and eg.classes[cc].nodes:
            for cn in list(eg.classes[cc].nodes)[:1]:
                print_node(eg, cn, indent + 1)

N = 8
eg = EGraph()
ensure_constants(eg)
ins = {}
for name in [f'a{i}' for i in range(N)] + [f'b{i}' for i in range(N)] + ['cin']:
    ins[name] = eg.make_class()

carry = ins['cin']
carry_ids = []

for i in range(N):
    a = ins[f'a{i}']
    b = ins[f'b{i}']
    g = eg.add(ENode(Op.AND, (a, b)))
    p = eg.add(ENode(Op.XOR, (a, b)))
    pc = eg.add(ENode(Op.AND, (p, carry)))
    carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))
    carry_ids.append(eg.find(carry))

outputs = {'cout': eg.find(carry)}
for i in range(N):
    outputs[f's{i}'] = eg.find(ins[f'a{i}'])

print(f"Initial classes: {len(eg.classes)}")

for it in range(5):
    before = len(eg.classes)
    for _, fn in RULES:
        fn(eg)
    eg.rebuild()
    eg.clear_changed()
    if len(eg.classes) == before:
        break

cout_cid = eg.find(outputs['cout'])
ecls = eg.classes.get(cout_cid)
print(f"\nCout e-class ({len(ecls.nodes)} implementations):")
for i, node in enumerate(list(ecls.nodes)):
    print(f"\n--- impl {i} ---")
    print_node(eg, node)

print(f"\nAll carry e-classes:")
for ci in carry_ids:
    cid = eg.find(ci)
    n = len(eg.classes[cid].nodes) if cid in eg.classes else 0
    print(f"  c{cid}: {n} impls")
