"""
Rewrite rules for gate-level synthesis.
Each rule = (name, pattern_fn, apply_fn).

Patterns match e-nodes in the e-graph.
Apply functions add new equivalent e-nodes to the matched e-class.
"""

from .gate_ir import Op, GateNode
from .egraph import EGraph, ENode


# ============================================================
# Helper: create a constant e-class
# ============================================================

LITERAL_CLASSES: dict[int, int] = {}  # value → e-class id


def literal(eg: EGraph, value: int) -> int:
    """Get or create an e-class for a constant bit value."""
    global LITERAL_CLASSES
    if value not in LITERAL_CLASSES:
        # Represent as a special "LIT" node using XOR with itself (XOR(x,x)=0 represents 0)
        # For simplicity, we use a sentinel: 0 = first constant, 1 = second
        if value == 0:
            # Create a zero: any XOR(x,x) 
            cid = eg.make_class()
            LITERAL_CLASSES[0] = cid
        else:
            cid = eg.make_class()
            LITERAL_CLASSES[1] = cid
    return LITERAL_CLASSES[value]


ZERO_CLASS = None
ONE_CLASS = None


def ensure_constants(eg: EGraph):
    """Initialize constant e-classes 0 and 1."""
    global ZERO_CLASS, ONE_CLASS
    if ZERO_CLASS is None:
        ZERO_CLASS = eg.make_class()
        ONE_CLASS = eg.make_class()


# ============================================================
# Rule definitions
# ============================================================

RULES = []


def rule(name):
    """Decorator to register a rewrite rule."""
    def decorator(fn):
        RULES.append((name, fn))
        return fn
    return decorator


@rule("and_commute")
def and_commute(eg: EGraph):
    """A & B = B & A"""
    matches = eg.ematch(lambda n: n.op == Op.AND and len(n.children) == 2)
    for cid, node in matches:
        swapped = ENode(Op.AND, (node.children[1], node.children[0]))
        eg.add(swapped)
        eg.union(cid, eg.hashcons.get(swapped, cid))


@rule("or_commute")
def or_commute(eg: EGraph):
    """A | B = B | A"""
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    for cid, node in matches:
        swapped = ENode(Op.OR, (node.children[1], node.children[0]))
        eg.add(swapped)
        eg.union(cid, eg.hashcons.get(swapped, cid))


@rule("xor_commute")
def xor_commute(eg: EGraph):
    """A ^ B = B ^ A"""
    matches = eg.ematch(lambda n: n.op == Op.XOR and len(n.children) == 2)
    for cid, node in matches:
        swapped = ENode(Op.XOR, (node.children[1], node.children[0]))
        eg.add(swapped)
        eg.union(cid, eg.hashcons.get(swapped, cid))


@rule("xor_assoc")
def xor_assoc(eg: EGraph):
    """(A ^ B) ^ C = A ^ (B ^ C)"""
    matches = eg.ematch(lambda n: n.op == Op.XOR and len(n.children) == 2)
    for cid, node in matches:
        a, b = node.children
        # Check if b is itself an XOR
        b_class = eg.find(b)
        if b_class not in eg.classes:
            continue
        for inner in list(eg.classes[b_class].nodes):
            if inner.op == Op.XOR and len(inner.children) == 2:
                b1, b2 = inner.children
                # Left-assoc: (A ^ (B1 ^ B2))
                left = ENode(Op.XOR, (a, b1))
                left_cid = eg.add(left)
                assoc = ENode(Op.XOR, (eg.find(left_cid), b2))
                eg.add(assoc)
                target = eg.find(eg.hashcons.get(assoc, -1))
                if target >= 0:
                    eg.union(cid, target)


@rule("and_assoc")
def and_assoc(eg: EGraph):
    """(A & B) & C = A & (B & C)"""
    matches = eg.ematch(lambda n: n.op == Op.AND and len(n.children) == 2)
    for cid, node in matches:
        a, b = node.children
        b_class = eg.find(b)
        if b_class not in eg.classes:
            continue
        for inner in list(eg.classes[b_class].nodes):
            if inner.op == Op.AND and len(inner.children) == 2:
                b1, b2 = inner.children
                left = ENode(Op.AND, (a, b1))
                left_cid = eg.add(left)
                assoc = ENode(Op.AND, (eg.find(left_cid), b2))
                eg.add(assoc)


@rule("or_assoc")
def or_assoc(eg: EGraph):
    """(A | B) | C = A | (B | C)"""
    matches = eg.ematch(lambda n: n.op == Op.OR and len(n.children) == 2)
    for cid, node in matches:
        a, b = node.children
        b_class = eg.find(b)
        if b_class not in eg.classes:
            continue
        for inner in list(eg.classes[b_class].nodes):
            if inner.op == Op.OR and len(inner.children) == 2:
                b1, b2 = inner.children
                left = ENode(Op.OR, (a, b1))
                left_cid = eg.add(left)
                assoc = ENode(Op.OR, (eg.find(left_cid), b2))
                eg.add(assoc)


@rule("not_not")
def not_not(eg: EGraph):
    """~~A = A"""
    matches = eg.ematch(lambda n: n.op == Op.NOT and len(n.children) == 1)
    for cid, node in matches:
        child = node.children[0]
        child_class = eg.find(child)
        if child_class not in eg.classes:
            continue
        for inner in list(eg.classes[child_class].nodes):
            if inner.op == Op.NOT and len(inner.children) == 1:
                # ~~A → A
                eg.union(cid, eg.find(inner.children[0]))


@rule("de_morgan_and")
def de_morgan_and(eg: EGraph):
    """~(A & B) = ~A | ~B"""
    matches = eg.ematch(lambda n: n.op == Op.NOT and len(n.children) == 1)
    for cid, node in matches:
        child = node.children[0]
        child_class = eg.find(child)
        if child_class not in eg.classes:
            continue
        for inner in list(eg.classes[child_class].nodes):
            if inner.op == Op.AND and len(inner.children) == 2:
                na = eg.add(ENode(Op.NOT, (inner.children[0],)))
                nb = eg.add(ENode(Op.NOT, (inner.children[1],)))
                or_node = eg.add(ENode(Op.OR, (eg.find(na), eg.find(nb))))
                target = eg.find(or_node)
                if target >= 0:
                    eg.union(cid, target)


@rule("de_morgan_or")
def de_morgan_or(eg: EGraph):
    """~(A | B) = ~A & ~B"""
    matches = eg.ematch(lambda n: n.op == Op.NOT and len(n.children) == 1)
    for cid, node in matches:
        child = node.children[0]
        child_class = eg.find(child)
        if child_class not in eg.classes:
            continue
        for inner in list(eg.classes[child_class].nodes):
            if inner.op == Op.OR and len(inner.children) == 2:
                na = eg.add(ENode(Op.NOT, (inner.children[0],)))
                nb = eg.add(ENode(Op.NOT, (inner.children[1],)))
                and_node = eg.add(ENode(Op.AND, (eg.find(na), eg.find(nb))))
                target = eg.find(and_node)
                if target >= 0:
                    eg.union(cid, target)


@rule("and_idempotent")
def and_idempotent(eg: EGraph):
    """A & A = A"""
    matches = eg.ematch(lambda n: n.op == Op.AND and n.children[0] == n.children[1])
    for cid, _ in matches:
        eg.union(cid, eg.find(matches[0][1].children[0]))


@rule("or_idempotent")
def or_idempotent(eg: EGraph):
    """A | A = A"""
    matches = eg.ematch(lambda n: n.op == Op.OR and n.children[0] == n.children[1])
    for cid, _ in matches:
        eg.union(cid, eg.find(matches[0][1].children[0]))


@rule("xor_self_zero")
def xor_self_zero(eg: EGraph):
    """A ^ A = 0"""
    matches = eg.ematch(lambda n: n.op == Op.XOR and n.children[0] == n.children[1])
    for cid, _ in matches:
        ensure_constants(eg)
        eg.union(cid, ZERO_CLASS)


def apply_all(eg: EGraph, max_iter: int = 10) -> int:
    """Apply all rewrite rules until saturation. Returns number of iterations."""
    for iteration in range(max_iter):
        before = len(eg.classes)
        for name, rule_fn in RULES:
            rule_fn(eg)
            eg.rebuild()
        after = len(eg.classes)
        eg.clear_changed()
        if before == after:
            return iteration + 1
    return max_iter
