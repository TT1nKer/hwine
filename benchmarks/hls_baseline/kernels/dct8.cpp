// Vivado HLS C++ kernel: DCT 8-point transform
// Matches the DCT benchmark in hwine-rs examples/bench_real.rs
//
// CSD constant decomposition is NOT performed by HLS; Vivado HLS will
// synthesize 8 DSP48E1 multipliers for the coefficient multiplications.
// hwine's e-graph discovers CSD automatically and eliminates all DSPs.

#include <ap_int.h>

typedef ap_int<16> data_t;

void dct8(
    data_t in[8],
    data_t out[8]
) {
    #pragma HLS INTERFACE ap_memory port=in
    #pragma HLS INTERFACE ap_memory port=out
    #pragma HLS INTERFACE s_axilite port=return

    // DCT Type-II coefficients (8-bit scaled integer)
    static const data_t coeff[8] = {
        181, 251, 213, 142, 256, 107, 71, 25
    };

    for (int i = 0; i < 8; i++) {
        #pragma HLS UNROLL
        data_t sum = 0;
        for (int j = 0; j < 8; j++) {
            #pragma HLS UNROLL
            sum += in[j] * coeff[j];
        }
        out[i] = sum;
    }
}
