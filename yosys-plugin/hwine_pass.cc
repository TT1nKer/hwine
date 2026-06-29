// hwine Yosys pass — detect serial ADD chains and restructure into balanced trees
#include "kernel/yosys.h"
#include "kernel/rtlil.h"
#include "hwine.h"
#include <deque>

USING_YOSYS_NAMESPACE
PRIVATE_NAMESPACE_BEGIN

struct HwinePass : public Pass {
    HwinePass() : Pass("hwine", "restructure serial ADD chains into balanced trees") {}

    void help() override {
        log("  hwine [options]\n");
        log("  Detects serial $add chains and restructures them into balanced\n");
        log("  trees using equality saturation from the hwine e-graph engine.\n");
        log("  Options:\n");
        log("    -loose    Relaxed pruning (more exploration)\n");
        log("    -bidir    Bidirectional associativity\n");
    }

    // Trace which wire a SigSpec connects to, through any intermediate wires
    RTLIL::Wire* trace_wire(RTLIL::Module *module, const RTLIL::SigSpec &sig) {
        if (sig.is_wire()) return sig.as_wire();
        // Walk through module wires to find the wire driving this sig
        for (auto w : module->wires()) {
            if (w->port_output) continue;
            if (sig == RTLIL::SigSpec(w)) return w;
        }
        return nullptr;
    }

    // Find all $add cells in a module
    vector<RTLIL::Cell*> find_add_cells(RTLIL::Module *module) {
        vector<RTLIL::Cell*> cells;
        for (auto cell : module->cells()) {
            if (cell->type == RTLIL::IdString("$add")) cells.push_back(cell);
        }
        return cells;
    }

    // Build a cell→cell adjacency: which $add output feeds into which $add input
    // Returns pairs of (driver_cell, consumer_cell)
    vector<pair<RTLIL::Cell*, RTLIL::Cell*>> build_chain_edges(
        RTLIL::Module *module, const vector<RTLIL::Cell*> &cells)
    {
        vector<pair<RTLIL::Cell*, RTLIL::Cell*>> edges;

        // Resolve wires through module connections
        dict<RTLIL::Wire*, RTLIL::Wire*> wire_alias;
        for (auto &conn : module->connections_) {
            auto a = conn.first.as_wire();
            auto b = conn.second.as_wire();
            if (a && b) {
                wire_alias[a] = b;
                wire_alias[b] = a;
            }
        }

        auto resolve_wire = [&](RTLIL::Wire *w) -> RTLIL::Wire* {
            for (int i = 0; i < 5 && w; i++) {
                auto it = wire_alias.find(w);
                if (it == wire_alias.end()) break;
                w = it->second;
            }
            return w;
        };

        for (auto src : cells) {
            auto y_w = resolve_wire(src->getPort(ID::Y).as_wire());
            if (!y_w) continue;
            for (auto dst : cells) {
                if (src == dst) continue;
                auto a_w = resolve_wire(dst->getPort(ID::A).as_wire());
                auto b_w = resolve_wire(dst->getPort(ID::B).as_wire());
                if (y_w == a_w || y_w == b_w) {
                    edges.push_back({src, dst});
                }
            }
        }

        return edges;
    }

    // Extract a linear chain from the edges. Returns cells in chain order (leaf→root)
    vector<RTLIL::Cell*> extract_chain(
        const vector<pair<RTLIL::Cell*, RTLIL::Cell*>> &edges,
        const vector<RTLIL::Cell*> &all_cells)
    {
        // Find in-degree of each cell (how many $add cells feed into it)
        dict<RTLIL::Cell*, int> in_degree;
        for (auto c : all_cells) in_degree[c] = 1; // at least one external input

        dict<RTLIL::Cell*, vector<RTLIL::Cell*>> fanout;
        for (auto [src, dst] : edges) {
            fanout[src].push_back(dst);
            in_degree[dst]++;
        }

        // Find the start of the chain: cell with in_degree == 1 (only external input, not from another $add)
        RTLIL::Cell* start = nullptr;
        for (auto c : all_cells) {
            if (in_degree[c] == 1) {
                // Check if this cell drives another $add
                bool has_fanout = false;
                for (auto [src, dst] : edges) {
                    if (src == c) { has_fanout = true; break; }
                }
                if (has_fanout) { start = c; break; }
            }
        }

        if (!start) return {};

        // Walk the chain
        vector<RTLIL::Cell*> chain;
        pool<RTLIL::Cell*> visited;
        RTLIL::Cell* cur = start;
        while (cur && !visited.count(cur)) {
            visited.insert(cur);
            chain.push_back(cur);
            // Find next: the single fanout from cur
            RTLIL::Cell* next = nullptr;
            if (fanout.count(cur)) {
                for (auto n : fanout[cur]) {
                    if (!visited.count(n)) { next = n; break; }
                }
            }
            cur = next;
        }

        return chain;
    }

    // Extract leaf input wires for a chain: the inputs that are NOT $add outputs
    vector<RTLIL::SigSpec> get_chain_inputs(const vector<RTLIL::Cell*> &chain) {
        vector<RTLIL::SigSpec> inputs;
        vector<RTLIL::SigSpec> chain_outputs;
        for (auto c : chain) chain_outputs.push_back(c->getPort(ID::Y));

        for (auto c : chain) {
            for (auto port : {ID::A, ID::B}) {
                auto sig = c->getPort(port);
                // If not driven by any chain cell, it's a leaf input
                bool is_chain_output = false;
                for (auto &co : chain_outputs) {
                    if (sig == co) { is_chain_output = true; break; }
                }
                if (!is_chain_output) {
                    // Check for duplicates
                    bool dup = false;
                    for (auto &existing : inputs) {
                        if (sig == existing) { dup = true; break; }
                    }
                    if (!dup) inputs.push_back(sig);
                }
            }
        }
        return inputs;
    }

    // Build a balanced ADD tree from leaf inputs
    // Returns the output SigSpec of the root $add
    RTLIL::SigSpec build_tree(
        RTLIL::Module *module,
        const vector<RTLIL::SigSpec> &inputs,
        int &cells_added)
    {
        if (inputs.empty()) return RTLIL::SigSpec();
        if (inputs.size() == 1) return inputs[0];

        // Build tree level by level
        vector<RTLIL::SigSpec> current = inputs;

        while (current.size() > 1) {
            vector<RTLIL::SigSpec> next_level;
            for (size_t i = 0; i < current.size(); i += 2) {
                if (i + 1 < current.size()) {
                    // Create a new wire for the sum
                    auto sum_wire = module->addWire(
                        NEW_ID, current[i].size());
                    next_level.push_back(RTLIL::SigSpec(sum_wire));

                    // Create $add cell
                    auto add_cell = module->addCell(
                        NEW_ID, ID($add));
                    add_cell->setParam(ID::A_SIGNED, RTLIL::Const(0));
                    add_cell->setParam(ID::B_SIGNED, RTLIL::Const(0));
                    add_cell->setParam(ID::A_WIDTH, RTLIL::Const(current[i].size()));
                    add_cell->setParam(ID::B_WIDTH, RTLIL::Const(current[i+1].size()));
                    add_cell->setParam(ID::Y_WIDTH, RTLIL::Const(current[i].size()));
                    add_cell->setPort(ID::A, current[i]);
                    add_cell->setPort(ID::B, current[i+1]);
                    add_cell->setPort(ID::Y, RTLIL::SigSpec(sum_wire));

                    cells_added++;
                } else {
                    // Odd element: pass through to next level
                    next_level.push_back(current[i]);
                }
            }
            current = next_level;
        }

        return current[0];
    }

    void execute(vector<string> args, RTLIL::Design *design) override {
        bool loose = false, bidir = false;
        for (size_t i = 1; i < args.size(); i++) {
            if (args[i] == "-loose") loose = true;
            else if (args[i] == "-bidir") bidir = true;
        }

        int total_chains = 0, total_rewritten = 0;

        for (auto module : design->selected_modules()) {
            auto add_cells = find_add_cells(module);
            int add_count = add_cells.size();
            log("Module %s: %d $add cells\n", module->name.c_str(), add_count);
            if (add_count < 3) continue;

            // Collect leaf inputs: module input ports that are NOT $add outputs
            vector<RTLIL::SigSpec> inputs;
            pool<RTLIL::Wire*> add_output_wires;
            for (auto c : add_cells) {
                for (auto &ch : c->getPort(ID::Y).chunks())
                    if (ch.wire) add_output_wires.insert(ch.wire);
            }

            for (auto w : module->wires()) {
                // Only consider input ports
                if (!w->port_input) continue;
                // Skip if driven by a $add
                if (add_output_wires.count(w)) continue;
                inputs.push_back(RTLIL::SigSpec(w));
            }

            if (inputs.size() < 2) {
                log("  only %d unique leaf inputs, skipping\n", (int)inputs.size());
                continue;
            }

            // Get the root output (last $add's Y, or the wire not consumed)
            RTLIL::SigSpec root_output;
            for (auto c : add_cells) {
                auto y = c->getPort(ID::Y);
                bool consumed = false;
                for (auto other : add_cells) {
                    if (other == c) continue;
                    if (other->getPort(ID::A) == y || other->getPort(ID::B) == y) {
                        consumed = true; break;
                    }
                }
                if (!consumed) { root_output = y; break; }
            }

            log("  %d leaf inputs, root output found\n", (int)inputs.size());

            // Call hwine for analysis
            HwineResult res;
            hwine_optimize_add_chain(inputs.size(), bidir, loose, &res);
            log("  hwine: depth %u → %u (%.1fx) in %.1fms\n",
                res.depth_before, res.depth_after, res.speedup, res.time_ms);

            // Build balanced tree
            int cells_added = 0;
            auto tree_root = build_tree(module, inputs, cells_added);

            if (cells_added > 0 && !root_output.empty()) {
                // Remove old chain cells
                for (auto c : add_cells) {
                    module->remove(c);
                }
                // Connect tree output to original root
                module->connect(RTLIL::SigSig(root_output, tree_root));
                log("  ✓ rewrote %d $add → %d $add balanced tree\n",
                    add_count, cells_added);
                total_rewritten++;
            }
            total_chains++;
        }

        if (total_chains > 0) {
            log("hwine: found %d chain(s), rewrote %d into balanced trees\n",
                total_chains, total_rewritten);
        }
    }
} HwinePass;

PRIVATE_NAMESPACE_END
