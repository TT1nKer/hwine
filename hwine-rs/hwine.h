// hwine C API — callable from C/C++ (Yosys pass)
#ifndef HWINE_H
#define HWINE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    uint32_t nodes_before;
    uint32_t nodes_after;
    uint32_t depth_before;
    uint32_t depth_after;
    double   time_ms;
    double   speedup;
} HwineResult;

/// Optimize an ADD chain
int hwine_optimize_add_chain(uint32_t n_inputs, int bidir, int loose, HwineResult* result);

/// Optimize a graph described as edge list [parent, child]
int hwine_optimize_graph(const uint32_t (*edges)[2], uint32_t n_edges, uint32_t n_nodes, HwineResult* result);

/// Get version
char* hwine_version(void);
void  hwine_free_string(char* s);

#ifdef __cplusplus
}
#endif

#endif
