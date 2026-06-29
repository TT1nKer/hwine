import sys, time
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES, rule

@rule("carry_group")
def carry_group(eg):
    """No match limit — process ALL OR nodes to create group equivalents."""
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

for N in [8, 16]:
    t0 = time.time()
    eg = EGraph()
    ensure_constants(eg)
    ins = {}
    for name in [f'a{i}' for i in range(N)] + [f'b{i}' for i in range(N)] + ['cin']:
        ins[name] = eg.make_class()
    carry = ins['cin']
    carry_ids = []
    outputs = {}
    for i in range(N):
        a = ins[f'a{i}']
        b = ins[f'b{i}']
        g = eg.add(ENode(Op.AND, (a, b)))
        p = eg.add(ENode(Op.XOR, (a, b)))
        s = eg.add(ENode(Op.XOR, (p, carry)))
        outputs[f's{i}'] = eg.find(s)
        pc = eg.add(ENode(Op.AND, (p, carry)))
        carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))
        carry_ids.append(eg.find(carry))
    outputs['cout'] = eg.find(carry)

    print(f"\n{N}-bit initial: {len(eg.classes)} classes")
    for it in range(5):
        before = len(eg.classes)
        for _, fn in RULES:
            fn(eg)
        eg.rebuild()
        eg.clear_changed()
        after = len(eg.classes)
        print(f"  it{it}: {before} -> {after}")
        if after == before: break

    # Show cout implementations count
    cout_cid = eg.find(outputs['cout'])
    if cout_cid in eg.classes:
        n_impl = len(eg.classes[cout_cid].nodes)
        print(f"  cout: {n_impl} implementations")
        for node in list(eg.classes[cout_cid].nodes):
            print(f"    {str(node)[:100]}")

    # Show each carry bit's implementation count
    print(f"  carry chain implementations:")
    for i, ci in enumerate(carry_ids):
        cid = eg.find(ci)
        n = len(eg.classes[cid].nodes) if cid in eg.classes else 0
        print(f"    c{i+1}: {n} impls")

    t = time.time() - t0
    print(f"  time: {t:.2f}s")
