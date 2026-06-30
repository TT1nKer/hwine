// Vivado HLS C++ kernel: FFT Butterfly complex multiply
// Matches the FFT benchmark in hwine-rs examples/bench_real.rs
//
// HLS produces 4-MUL direct form (4 DSP48).
// hwine's e-graph discovers the Gauss 3-MUL form as an alternative.

#include <ap_int.h>

typedef ap_int<16> data_t;

void fft_butterfly(
    data_t ar,   // real part of a
    data_t ai,   // imag part of a
    data_t br,   // real part of b
    data_t bi,   // imag part of b
    data_t *out_real,
    data_t *out_imag
) {
    #pragma HLS INTERFACE s_axilite port=ar
    #pragma HLS INTERFACE s_axilite port=ai
    #pragma HLS INTERFACE s_axilite port=br
    #pragma HLS INTERFACE s_axilite port=bi
    #pragma HLS INTERFACE s_axilite port=out_real
    #pragma HLS INTERFACE s_axilite port=out_imag
    #pragma HLS INTERFACE s_axilite port=return

    data_t ac = ar * br;
    data_t ad = ar * bi;
    data_t bc = ai * br;
    data_t bd = ai * bi;

    *out_real = ac - bd;  // (ar*br) - (ai*bi)
    *out_imag = ad + bc;  // (ar*bi) + (ai*br)
}
