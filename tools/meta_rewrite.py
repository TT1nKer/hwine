"""
Rewrite rules — FPGA-aware version.
Adds pipeline insertion and DSP-mapping rules.
"""

from .meta_ir import AtomOp, ENode, ASSOCIATIVE_OPS, COMMUTATIVE_OPS, FPGA_DELAY_NS
from .meta_egraph import EGraph


def _is_const(node: ENode, value: int) -> bool:
    return node.op == AtomOp.CONST and node.meta == value


# ─── Core algebraic rules ────────────────────────────────────

def rule_assoc(eg: EGraph):
    """OP(OP(a,b), c) → OP(a, OP(b,c)) — left→right only.
    Strict pruning: max 5 inner nodes, max 10 total nodes per class."""
    for op in ASSOCIATIVE_OPS:
        for cid in list(eg.changed):
            cid = eg._canon(cid)
            if cid not in eg.classes:
                continue
            ecls = eg.classes[cid]
            if len(ecls.nodes) > 10:
                continue
            for node in list(ecls.nodes)[:5]:  # only scan 5
                if node.op != op or len(node.children) != 2:
                    continue
                inner_cid = eg._canon(node.children[0])
                if inner_cid not in eg.classes:
                    continue
                inner_cls = eg.classes[inner_cid]
                if len(inner_cls.nodes) > 10:
                    continue
                for inner in list(inner_cls.nodes)[:5]:  # only scan 5
                    if inner.op != op or len(inner.children) != 2:
                        continue
                    a, b = inner.children[0], inner.children[1]
                    c = node.children[1]
                    bc_cid = eg.add(ENode(op, (b, c)))
                    new_node = ENode(op, (a, bc_cid))
                    new_cid = eg.add(new_node)
                    if new_cid != cid:
                        eg._union(new_cid, cid)
                    break


def rule_commute(eg: EGraph):
    for op in COMMUTATIVE_OPS:
        for cid in list(eg.changed):
            cid = eg._canon(cid)
            if cid not in eg.classes:
                continue
            for node in list(eg.classes[cid].nodes):
                if node.op != op or len(node.children) != 2:
                    continue
                a, b = node.children
                swapped = ENode(op, (b, a))
                eg._union(eg.add(swapped), cid)


def rule_mac_decompose(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.MAC or len(node.children) < 3:
                continue
            w, a, acc = node.children[0], node.children[1], node.children[2]
            mul_cid = eg.add(ENode(AtomOp.MUL, (w, a)))
            add_cid = eg.add(ENode(AtomOp.ADD, (mul_cid, acc)))
            eg._union(add_cid, cid)


def rule_mac_fuse(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.ADD or len(node.children) != 2:
                continue
            mul_cid, acc = node.children
            mul_cid = eg._canon(mul_cid)
            if mul_cid not in eg.classes:
                continue
            for mul_node in list(eg.classes[mul_cid].nodes):
                if mul_node.op == AtomOp.MUL and len(mul_node.children) == 2:
                    w, a = mul_node.children
                    mac_cid = eg.add(ENode(AtomOp.MAC, (w, a, acc)))
                    eg._union(mac_cid, cid)
                    break


def rule_add_identity(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.ADD or len(node.children) != 2:
                continue
            for i in range(2):
                side = eg._canon(node.children[i])
                if side not in eg.classes:
                    continue
                for ch in eg.classes[side].nodes:
                    if ch.op == AtomOp.ZERO or _is_const(ch, 0):
                        other = eg._canon(node.children[1 - i])
                        eg._union(other, cid)
                        break


def rule_mul_identity(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.MUL or len(node.children) != 2:
                continue
            for i in range(2):
                side = eg._canon(node.children[i])
                if side not in eg.classes:
                    continue
                for ch in eg.classes[side].nodes:
                    if ch.op == AtomOp.ONE or _is_const(ch, 1):
                        other = eg._canon(node.children[1 - i])
                        eg._union(other, cid)
                        break


def rule_mul_zero(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.MUL or len(node.children) != 2:
                continue
            for i in range(2):
                side = eg._canon(node.children[i])
                if side not in eg.classes:
                    continue
                for ch in eg.classes[side].nodes:
                    if ch.op == AtomOp.ZERO or _is_const(ch, 0):
                        zero_cid = eg.add(ENode(AtomOp.ZERO, ()))
                        eg._union(zero_cid, cid)
                        break


def rule_acc_to_reduce_tree(eg: EGraph):
    """ACC_STEP(ACC_STEP(init, v1), v2) == ACC_STEP(init, ADD(v1, v2)).
    Flatten nested accumulator chains. No ZERO guard needed."""
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        ecls = eg.classes[cid]
        if len(ecls.nodes) > 15:
            continue
        for node in list(ecls.nodes)[:8]:
            if node.op != AtomOp.ACC_STEP or len(node.children) != 2:
                continue
            prev, val2 = node.children
            p_cid = eg._canon(prev)
            if p_cid not in eg.classes:
                continue
            p_cls = eg.classes[p_cid]
            if len(p_cls.nodes) > 15:
                continue
            for inner in list(p_cls.nodes)[:8]:
                if inner.op != AtomOp.ACC_STEP or len(inner.children) != 2:
                    continue
                init, val1 = inner.children
                add_cid = eg.add(ENode(AtomOp.ADD, (val1, val2)))
                new_node = ENode(AtomOp.ACC_STEP, (init, add_cid))
                new_cid = eg.add(new_node)
                if new_cid != cid:
                    eg._union(new_cid, cid)
                break


# ─── FPGA-specific rules ─────────────────────────────────────

def rule_pipe_insert(eg: EGraph, threshold_ns: float = 3.0):
    """Insert PIPE register stages when combinational delay exceeds threshold.
    This is critical for FPGA timing closure.
    PIPE costs 0 LUTs, ~8 FFs, adds 1 cycle latency but raises fmax."""
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        ecls = eg.classes[cid]
        if len(ecls.nodes) > 20:
            continue
        for node in list(ecls.nodes):
            # Only insert PIPE after expensive ops
            op_delay = FPGA_DELAY_NS.get(node.op, 0)
            if op_delay < threshold_ns * 0.3:
                continue
            # Don't pipe already-piped or trivial nodes
            if node.op in (AtomOp.PIPE, AtomOp.DELAY, AtomOp.VAR, AtomOp.CONST,
                           AtomOp.ZERO, AtomOp.ONE, AtomOp.STR_LIT):
                continue
            # Insert PIPE after this node
            piped_cid = eg.add(ENode(AtomOp.PIPE, (cid,)))
            # Mark equivalence: this node's output ≡ piped version (1 cycle later)
            # We don't union (different latency!) — just add the alternative representation
            # The extraction phase will pick based on area/delay tradeoff
            # For now, add it to the parent classes
            for parent_cid in list(eg.parents_of.get(cid, set())):
                parent_cid = eg._canon(parent_cid)
                if parent_cid in eg.classes:
                    for pnode in list(eg.classes[parent_cid].nodes):
                        # If parent has cid as child, create equivalent with piped version
                        new_children = []
                        for ch in pnode.children:
                            if eg._canon(ch) == cid:
                                new_children.append(piped_cid)
                            else:
                                new_children.append(ch)
                        if any(eg._canon(c) != old_c for c, old_c in zip(new_children, pnode.children)):
                            alt_node = ENode(pnode.op, tuple(new_children), pnode.meta)
                            alt_cid = eg.add(alt_node)
                            eg._union(alt_cid, parent_cid)
                            break


def rule_map_to_dsp(eg: EGraph):
    """Annotate MUL/MAC nodes as DSP candidates for FPGA extraction.
    MUL → DSP_MUL, MAC → DSP_MAC.
    DSP_MUL and DSP_MAC have different FPGA costs (LUT=0, DSP=1)."""
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op == AtomOp.MUL and len(node.children) == 2:
                a, b = node.children
                dsp_cid = eg.add(ENode(AtomOp.DSP_MUL, (a, b)))
                eg._union(dsp_cid, cid)
            elif node.op == AtomOp.MAC and len(node.children) == 3:
                w, a, acc = node.children
                dsp_cid = eg.add(ENode(AtomOp.DSP_MAC, (w, a, acc)))
                eg._union(dsp_cid, cid)


def rule_delay_promote(eg: EGraph):
    """Promote multi-PIPE chains into a single DELAY for cleaner extraction.
    PIPE(PIPE(x)) → DELAY(x, 2)"""
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.PIPE or len(node.children) != 1:
                continue
            inner_cid = eg._canon(node.children[0])
            if inner_cid not in eg.classes:
                continue
            for inner in eg.classes[inner_cid].nodes:
                if inner.op == AtomOp.PIPE and len(inner.children) == 1:
                    # PIPE(PIPE(x)) → DELAY(x, 2)
                    x = inner.children[0]
                    const2 = eg.add(ENode(AtomOp.CONST, (), 2))
                    delay_cid = eg.add(ENode(AtomOp.DELAY, (x, const2)))
                    eg._union(delay_cid, cid)
                    break


def rule_shift_combine(eg: EGraph):
    for shift_op in (AtomOp.SHL, AtomOp.SHR):
        for cid in list(eg.changed):
            cid = eg._canon(cid)
            if cid not in eg.classes:
                continue
            for node in list(eg.classes[cid].nodes):
                if node.op != shift_op or len(node.children) != 2:
                    continue
                inner_cid, n = node.children
                inner_cid = eg._canon(inner_cid)
                if inner_cid not in eg.classes:
                    continue
                for inner in eg.classes[inner_cid].nodes:
                    if inner.op == shift_op and len(inner.children) == 2:
                        x, m = inner.children
                        combined = None
                        for a_n in eg.classes[eg._canon(n)].nodes:
                            for a_m in eg.classes[eg._canon(m)].nodes:
                                if a_n.op == AtomOp.CONST and a_m.op == AtomOp.CONST:
                                    total = a_n.children[0] + a_m.children[0]
                                    const_cid = eg.add(ENode(AtomOp.CONST, (), total))
                                    combined_cid = eg.add(ENode(shift_op, (x, const_cid)))
                                    eg._union(combined_cid, cid)
                                    combined = True
                        if combined:
                            break


def rule_quant_fold(eg: EGraph):
    for cid in list(eg.changed):
        cid = eg._canon(cid)
        if cid not in eg.classes:
            continue
        for node in list(eg.classes[cid].nodes):
            if node.op != AtomOp.MUL or len(node.children) != 2:
                continue
            for w_side, act_side in [(0, 1), (1, 0)]:
                w_cid = eg._canon(node.children[w_side])
                if w_cid not in eg.classes:
                    continue
                for w_node in eg.classes[w_cid].nodes:
                    if w_node.op == AtomOp.DEQUANT_W and len(w_node.children) == 3:
                        int4, scale, zp = w_node.children
                        act = node.children[act_side]
                        mul_cid = eg.add(ENode(AtomOp.MUL, (int4, act)))
                        eg._union(mul_cid, cid)
                        break


# ─── Rule sets ───────────────────────────────────────────────

CORE_RULES = [
    rule_assoc, rule_commute,
    rule_mac_decompose, rule_mac_fuse,
    rule_add_identity, rule_mul_identity, rule_mul_zero,
    rule_acc_to_reduce_tree,
    rule_shift_combine, rule_quant_fold,
]

FPGA_RULES = [
    rule_map_to_dsp,
    rule_pipe_insert,
    rule_delay_promote,
]

ALL_RULES = CORE_RULES + FPGA_RULES

FAST_RULES = [
    rule_assoc,
    rule_mac_decompose, rule_mac_fuse,
    rule_add_identity, rule_mul_identity,
    rule_acc_to_reduce_tree,
    rule_map_to_dsp,
]
