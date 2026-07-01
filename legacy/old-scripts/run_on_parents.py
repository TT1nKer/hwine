import sys, time
sys.path.insert(0, r"C:\hwine")

from tools.meta_ir import AtomOp, ENode
from tools.meta_egraph import EGraph
from tools.meta_rewrite import FAST_RULES

def log(s):
    print(s, flush=True)

# Demo 1: N=8 ADD chain
log("=" * 50)
log("Demo 1: 8-wide ADD chain -> tree")
eg = EGraph()
N = 8
vs = [eg.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
chain = vs[0]
for i in range(1, N):
    chain = eg.add(ENode(AtomOp.ADD, (chain, vs[i])))
log(f"  Initial: {len(eg.classes)} classes")
t0 = time.time()
iters = eg.saturate(FAST_RULES, max_iter=15)
dt = time.time() - t0
cid = eg._canon(chain)
_, d = eg.extract_depth(cid)
log(f"  {iters} iters, {len(eg.classes)} classes, {eg.union_count} unions, {dt:.3f}s")
log(f"  Serial depth {N-1} -> best depth {int(d)}")

# Demo 2: 8-way int4 MAC tile
log("")
log("=" * 50)
log("Demo 2: 8-way int4 MAC tile")
eg2 = EGraph()
n_macs = 8
zero = eg2.add(ENode(AtomOp.ZERO, ()))
vs_w = [eg2.add(ENode(AtomOp.VAR, (f"w{i}",))) for i in range(n_macs)]
vs_a = [eg2.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(n_macs)]
acc_init = eg2.add(ENode(AtomOp.ACC_INIT, (zero,)))
acc_state = acc_init
mac_chain = acc_init
for i in range(n_macs):
    mul = eg2.add(ENode(AtomOp.MUL, (vs_w[i], vs_a[i])))
    acc_state = eg2.add(ENode(AtomOp.ACC_STEP, (acc_state, mul)))
    mac_chain = eg2.add(ENode(AtomOp.MAC, (vs_w[i], vs_a[i], mac_chain)))
eg2._union(acc_state, mac_chain)
target = eg2._canon(acc_state)
log(f"  Initial: {len(eg2.classes)} classes")
t0 = time.time()
iters = eg2.saturate(FAST_RULES, max_iter=15)
dt = time.time() - t0
cid = eg2._canon(target)
n_repr = len(eg2.classes[cid].nodes)
_, d = eg2.extract_depth(cid)
log(f"  {iters} iters, {len(eg2.classes)} classes, {eg2.union_count} unions, {dt:.3f}s")
log(f"  {n_repr} reprs, serial depth 10 -> best depth {int(d)}")

# Demo 3: N scaling (small)
log("")
log("=" * 50)
log("Demo 3: Scaling")
for N in [4, 6, 8, 10, 12]:
    eg3 = EGraph()
    vs = [eg3.add(ENode(AtomOp.VAR, (f"a{i}",))) for i in range(N)]
    c = vs[0]
    for i in range(1, N):
        c = eg3.add(ENode(AtomOp.ADD, (c, vs[i])))
    t0 = time.time()
    iters = eg3.saturate(FAST_RULES, max_iter=15)
    dt = time.time() - t0
    cid = eg3._canon(c)
    _, d = eg3.extract_depth(cid)
    log(f"  N={N:3d}: {iters:2d} iters, {len(eg3.classes):6d} classes, "
        f"{eg3.union_count:8d} unions, depth {N-1}->{int(d)}, {dt:.3f}s")

log("")
log("Done")
