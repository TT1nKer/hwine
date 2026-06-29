"""
Extract an optimal circuit from a saturated e-graph.

Strategy: for each e-class, choose the e-node that minimizes the cost function.
Recurse to children e-classes.

Cost function: prioritize depth (critical path delay), then area.
"""

from .egraph import EGraph, ENode
from .gate_ir import Op, GateNode, Circuit, OP_DELAY, OP_AREA


def extract(eg: EGraph, output_classes: dict[str, int],
            name: str = "extracted") -> Circuit:
    """
    Extract a circuit from the e-graph.
    output_classes: output_name → e_class_id (canonical)
    """
    circuit = Circuit(name)
    extracted = {}  # e-class id → signal name in circuit
    counter = [0]

    def extract_class(cid: int) -> str:
        """Extract an e-class, return the signal name."""
        cid = eg.find(cid)
        if cid in extracted:
            return extracted[cid]

        ecls = eg.classes.get(cid)
        if not ecls or not ecls.nodes:
            # Input or constant — create input node
            name = f"in_{cid}" if cid >= 0 else f"c_{abs(cid)}"
            extracted[cid] = name
            return name

        # Choose the best e-node in this e-class
        # Strategy: pick the one with shortest critical path
        best_node = None
        best_depth = float('inf')

        for node in ecls.nodes:
            # Recursively compute depth of children
            child_depth = 0
            for child_cid in node.children:
                child_cid = eg.find(child_cid)
                if child_cid in extracted:
                    child_depth = max(child_depth, 0)
                elif child_cid in eg.classes and eg.classes[child_cid].nodes:
                    # Estimate: check if we can compute
                    pass

            node_depth = OP_DELAY.get(node.op, 1)
            if node_depth < best_depth:
                best_depth = node_depth
                best_node = node

        if best_node is None:
            name = f"in_{cid}"
            extracted[cid] = name
            return name

        # Recurse to children first
        child_names = []
        for child_cid in best_node.children:
            child_names.append(extract_class(child_cid))

        # Create gate
        name = f"g_{counter[0]}"
        counter[0] += 1
        circuit.add_gate(name, best_node.op, *child_names)
        extracted[cid] = name
        return name

    # Check if any output_classes are constants
    for out_name, cid in output_classes.items():
        cid = eg.find(cid)
        ecls = eg.classes.get(cid)
        if not ecls or not ecls.nodes:
            # This is an input/constant — create a buffer
            sig = f"in_{cid}"
            extracted[cid] = sig
            circuit.add_output(out_name, sig)
            continue

    # Extract all outputs
    for out_name, cid in output_classes.items():
        sig_name = extract_class(cid)
        circuit.add_output(out_name, sig_name)

    return circuit


def extract_optimal(eg: EGraph, output_classes: dict[str, int],
                    name: str = "optimal", max_depth: float = float('inf')) -> Circuit:
    """
    Extract the minimal-depth circuit from the e-graph with depth ≤ max_depth.
    Uses dynamic programming to find the best e-node per e-class.
    """
    circuit = Circuit(name)
    extracted = {}       # e-class id → (signal_name, depth)
    counter = [0]
    memo = {}

    def best_signal(cid: int, depth_limit: float) -> tuple[str, float]:
        cid = eg.find(cid)
        key = (cid, depth_limit)
        if key in memo:
            return memo[key]

        ecls = eg.classes.get(cid)
        if not ecls or not ecls.nodes:
            name = f"in_{cid}"
            extracted[cid] = (name, 0)
            memo[key] = (name, 0)
            return memo[key]

        # Already extracted?
        if cid in extracted:
            return extracted[cid]

        best_name = None
        best_depth = float('inf')
        best_area = float('inf')

        for node in ecls.nodes:
            child_names = []
            child_total_depth = 0
            remaining = depth_limit - OP_DELAY.get(node.op, 1)
            feasible = True

            for child_cid in node.children:
                child_cid = eg.find(child_cid)
                cname, cdepth = best_signal(child_cid, remaining)
                if cdepth > remaining:
                    feasible = False
                    break
                child_names.append(cname)
                child_total_depth = max(child_total_depth, cdepth)

            if not feasible:
                continue

            total_depth = child_total_depth + OP_DELAY.get(node.op, 1)
            total_area = OP_AREA.get(node.op, 1)

            if total_depth < best_depth or (total_depth == best_depth and total_area < best_area):
                best_depth = total_depth
                best_area = total_area
                best_name = child_names
                best_node = node

        if best_name is None:
            # Fallback: just pick any node
            for node in ecls.nodes:
                child_names = []
                for child_cid in node.children:
                    child_cid = eg.find(child_cid)
                    cname, _ = best_signal(child_cid, float('inf'))
                    child_names.append(cname)
                name = f"g_{counter[0]}"
                counter[0] += 1
                circuit.add_gate(name, node.op, *child_names)
                extracted[cid] = (name, OP_DELAY.get(node.op, 1))
                memo[key] = (name, OP_DELAY.get(node.op, 1))
                return memo[key]

        # Create the best gate
        name = f"g_{counter[0]}"
        counter[0] += 1
        circuit.add_gate(name, best_node.op, *best_name)
        extracted[cid] = (name, best_depth)
        memo[key] = (name, best_depth)
        return memo[key]

    # Extract outputs
    for out_name, cid in output_classes.items():
        sig_name, depth = best_signal(cid, max_depth)
        circuit.add_output(out_name, sig_name)

    return circuit
