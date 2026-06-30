// Vivado HLS C++ kernel: GEMM dot product (N=8)
// Matches the Dot8 benchmark in hwine-rs examples/bench_real.rs
//
// HLS will produce a serial MAC chain (7 adder levels).
// hwine's associativity rule reduces to balanced tree (3 levels).

#include <ap_int.h>

typedef ap_int<16> data_t;

void gemm_dot8(
    data_t a[8],
    data_t b[8],
    data_t *result
) {
    #pragma HLS INTERFACE ap_memory port=a
    #pragma HLS INTERFACE ap_memory port=b
    #pragma HLS INTERFACE s_axilite port=result
    #pragma HLS INTERFACE s_axilite port=return

    data_t sum = 0;
    for (int i = 0; i < 8; i++) {
        #pragma HLS UNROLL
        sum += a[i] * b[i];
    }
    *result = sum;
}
