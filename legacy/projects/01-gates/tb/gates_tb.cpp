#include "Vgates.h"
#include "Vadder.h"
#include "Vdff.h"
#include "Vcounter.h"
#include "verilated.h"
#include "verilated_fst_c.h"
#include <cstdio>
#include <cstdlib>

vluint64_t sim_time = 0;

int test_gates(Vgates *top, VerilatedFstC *tfp) {
    printf("[test_gates]\n");
    int failures = 0;

    struct { int a, b; } cases[] = {
        {0x00, 0x00}, {0xFF, 0xFF}, {0x55, 0xAA},
        {0x0F, 0xF0}, {0x33, 0xCC}, {0x00, 0xFF}
    };

    for (int i = 0; i < 6; i++) {
        top->a = cases[i].a;
        top->b = cases[i].b;
        top->eval();

        int a = cases[i].a, b = cases[i].b;
        if (top->and_out  != (a & b))      failures++;
        if (top->or_out   != (a | b))      failures++;
        if (top->xor_out  != (a ^ b))      failures++;
        if (top->nand_out != (a & b) ^ 0xFF) failures++;
        if (top->nor_out  != (a | b) ^ 0xFF) failures++;
        if (top->xnor_out != (a ^ b) ^ 0xFF) failures++;

        tfp->dump(sim_time++);
    }
    printf("  gates: %d failures\n", failures);
    return failures;
}

int test_adder(Vadder *top, VerilatedFstC *tfp) {
    printf("[test_adder]\n");
    int failures = 0;

    for (int a = 0; a < 16 && failures < 10; a++) {
        for (int b = 0; b < 16 && failures < 10; b++) {
            top->a = a;
            top->b = b;
            top->cin = 0;
            top->eval();
            int expected = a + b;
            if (top->sum != (expected & 0xF) || top->cout != ((expected >> 4) & 1))
                failures++;

            top->cin = 1;
            top->eval();
            expected = a + b + 1;
            if (top->sum != (expected & 0xF) || top->cout != ((expected >> 4) & 1))
                failures++;
        }
        tfp->dump(sim_time++);
    }
    printf("  adder: %d failures\n", failures);
    return failures;
}

int test_dff(Vdff *top, VerilatedFstC *tfp) {
    printf("[test_dff]\n");
    int failures = 0;

    // Reset
    top->clk = 0; top->rst_n = 0; top->d = 0;
    top->eval(); tfp->dump(sim_time++);
    if (top->q != 0) failures++;

    // Release reset, set d=1
    top->rst_n = 1; top->d = 1;
    top->eval(); tfp->dump(sim_time++);
    // q should still be 0 (no clock edge yet)
    if (top->q != 0) failures++;

    // Clock pulse
    top->clk = 1; top->eval(); tfp->dump(sim_time++);
    if (top->q != 1) failures++;

    // Change d, no clock
    top->d = 0;
    top->clk = 0; top->eval(); tfp->dump(sim_time++);
    if (top->q != 1) failures++;

    // Another clock pulse — should capture d=0
    top->clk = 1; top->eval(); tfp->dump(sim_time++);
    if (top->q != 0) failures++;

    printf("  dff: %d failures\n", failures);
    return failures;
}

int test_counter(Vcounter *top, VerilatedFstC *tfp) {
    printf("[test_counter]\n");
    int failures = 0;

    // Reset
    top->clk = 0; top->rst_n = 0; top->enable = 0;
    top->eval(); tfp->dump(sim_time++);
    if (top->count != 0 || top->overflow != 0) failures++;

    // Release reset, enable counting
    top->rst_n = 1; top->enable = 1;
    top->eval(); tfp->dump(sim_time++);

    // Clock 16 times — should count 0..15, overflow at 16
    int prev = 0;
    for (int i = 0; i < 17; i++) {
        top->clk = 1; top->eval(); tfp->dump(sim_time++);
        if (i < 16) {
            if (top->count != (i + 1) % 16) failures++;
        }
        if (i == 15 && top->overflow != 1) failures++;
        if (i == 16 && top->overflow != 0 && top->count != 0) failures++;

        top->clk = 0; top->eval(); tfp->dump(sim_time++);
    }

    printf("  counter: %d failures\n", failures);
    return failures;
}

int main(int argc, char **argv) {
    Verilated::commandArgs(argc, argv);

    VerilatedFstC *tfp = new VerilatedFstC;
    tfp->open("build/sim.fst");

    int total_failures = 0;

    // --- gates ---
    Vgates *gates_top = new Vgates;
    gates_top->trace(tfp, 99);
    total_failures += test_gates(gates_top, tfp);
    gates_top->final();
    delete gates_top;

    // --- adder ---
    Vadder *adder_top = new Vadder;
    adder_top->trace(tfp, 99);
    total_failures += test_adder(adder_top, tfp);
    adder_top->final();
    delete adder_top;

    // --- dff ---
    Vdff *dff_top = new Vdff;
    dff_top->trace(tfp, 99);
    total_failures += test_dff(dff_top, tfp);
    dff_top->final();
    delete dff_top;

    // --- counter ---
    Vcounter *counter_top = new Vcounter;
    counter_top->trace(tfp, 99);
    total_failures += test_counter(counter_top, tfp);
    counter_top->final();
    delete counter_top;

    tfp->close();
    delete tfp;

    if (total_failures == 0) {
        printf("\n=== ALL TESTS PASSED ===\n");
    } else {
        printf("\n=== %d FAILURES ===\n", total_failures);
    }

    return total_failures > 0 ? 1 : 0;
}
