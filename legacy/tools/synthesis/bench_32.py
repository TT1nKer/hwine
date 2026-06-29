import sys, time
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

N = 32
t0 = time.time()
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
    s = eg.add(ENode(Op.XOR, (p, carry)))
    outputs[f's{i}'] = eg.find(s)
    pc = eg.add(ENode(Op.AND, (p, carry)))
    carry = eg.add(ENode(Op.OR, (g, eg.find(pc))))
outputs['cout'] = eg.find(carry)
print(f"Built: {len(eg.classes)} classes, {time.time()-t0:.2f}s")

ref = extract_optimal(eg, outputs, 'ref', max_depth=500)
print(f"Ref depth: {ref.depth():.1f}")

for it in range(5):
    before = len(eg.classes)
    for _, fn in RULES: fn(eg)
    eg.rebuild(); eg.clear_changed()
    print(f"  it{it}: {len(eg.classes)} classes")
    if len(eg.classes) == before: break

opt = extract_optimal(eg, outputs, 'opt', max_depth=500)
n_impls = len(eg.classes[eg.find(outputs['cout'])].nodes)
ripple = N * 3.0
prefix = (N.bit_length() - 1) * 3.0 + 2.5
impr = (1 - opt.depth()/ref.depth()) * 100
t = time.time() - t0
print(f"32-bit: n_impls={n_impls} ref={ref.depth():.1f} opt={opt.depth():.1f}")
print(f"  ripple={ripple:.1f} prefix={prefix:.1f} impr={impr:.0f}% time={t:.2f}s")
