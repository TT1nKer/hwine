import sys, time
sys.path.insert(0, '.')
from tools.synthesis.gate_ir import Op
from tools.synthesis.egraph import EGraph, ENode
from tools.synthesis.rewrite import ensure_constants, RULES, apply_all
from tools.synthesis.extract import extract_optimal

def node_depth(eg, node, visited=None):
    if visited is None:
        visited = set()
    nid = id(node)
    if nid in visited:
        return 0
    visited.add(nid)
    cd = {Op.AND: 1.5, Op.OR: 1.5, Op.XOR: 2.5, Op.NOT: 1.0}.get(node.op, 1)
    mc = 0
    for c in node.children:
        cc = eg.find(c)
        if cc in eg.classes and eg.classes[cc].nodes:
            for cn in eg.classes[cc].nodes:
                mc = max(mc, node_depth(eg, cn, visited.copy()))
    return mc + cd

for N in [8, 16, 32]:
    eg = EGraph()
    ensure_constants(eg)
    ins = {}
    for name in [f'a{i}' for i in range(N)] + [f'b{i}' for i in range(N)] + ['cin']:
        ins[name] = eg.make_class()
    carry = ins['cin']
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
    outputs['cout'] = eg.find(carry)

    ref = extract_optimal(eg, outputs, 'ref', max_depth=500)
    ref_d = ref.depth()

    apply_all(eg, max_iter=5)

    cid = eg.find(outputs['cout'])
    ecls = eg.classes.get(cid)
    depths = []
    if ecls:
        for n in ecls.nodes:
            depths.append(node_depth(eg, n))

    opt = extract_optimal(eg, outputs, 'opt', max_depth=500)
    opt_d = opt.depth()
    ripple_theory = N * 3.0
    prefix_theory = (N.bit_length() - 1) * 3.0 + 2.5
    print(f"{N}-bit: ripple_theory={ripple_theory:.1f} prefix_theory={prefix_theory:.1f}")
    print(f"  ref_extract_depth={ref_d:.1f} opt_extract_depth={opt_d:.1f}")
    print(f"  min_node_depth={min(depths):.1f} max_node_depth={max(depths):.1f}")
    print(f"  n_impl={len(depths)}")
