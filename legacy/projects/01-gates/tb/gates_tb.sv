// Testbench for basic gates, adder, DFF, counter
`timescale 1ns / 1ps

module tb;
    logic [7:0] a, b;
    logic [7:0] and_out, or_out, xor_out, nand_out, nor_out, xnor_out;

    logic [3:0] add_a, add_b;
    logic       add_cin;
    logic [3:0] add_sum;
    logic       add_cout;

    logic clk, rst_n, d, q;

    logic       cnt_enable;
    logic [3:0] cnt_count;
    logic       cnt_overflow;

    integer failures = 0;

    gates gates_inst (
        .a(a), .b(b),
        .and_out(and_out), .or_out(or_out), .xor_out(xor_out),
        .nand_out(nand_out), .nor_out(nor_out), .xnor_out(xnor_out)
    );

    adder adder_inst (
        .a(add_a), .b(add_b), .cin(add_cin),
        .sum(add_sum), .cout(add_cout)
    );

    dff dff_inst (
        .clk(clk), .rst_n(rst_n), .d(d), .q(q)
    );

    counter counter_inst (
        .clk(clk), .rst_n(rst_n), .enable(cnt_enable),
        .count(cnt_count), .overflow(cnt_overflow)
    );

    always #5 clk = ~clk;

    // macros for clean assertions
    `define ASSERT(cond, msg) if (!(cond)) begin failures++; $display("FAIL %s", msg); end
    `define ASSERT_EQ(actual, expected, name) if ((actual) !== (expected)) begin failures++; $display("FAIL [%s]: got %0d, expected %0d", name, actual, expected); end

    initial begin
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);
        clk = 0; rst_n = 0;

        // ==================== test gates ====================
        $display("[test_gates]");

        a = 8'h00; b = 8'h00; #1;
        `ASSERT(and_out == 8'h00, "gates 00&00 and");
        `ASSERT(or_out  == 8'h00, "gates 00&00 or");
        `ASSERT(xor_out == 8'h00, "gates 00&00 xor");
        `ASSERT(nand_out == 8'hFF, "gates 00&00 nand");
        `ASSERT(nor_out  == 8'hFF, "gates 00&00 nor");
        `ASSERT(xnor_out == 8'hFF, "gates 00&00 xnor");

        a = 8'hFF; b = 8'hFF; #1;
        `ASSERT(and_out == 8'hFF, "gates FF&FF and");
        `ASSERT(or_out  == 8'hFF, "gates FF&FF or");
        `ASSERT(xor_out == 8'h00, "gates FF&FF xor");
        `ASSERT(nand_out == 8'h00, "gates FF&FF nand");
        `ASSERT(nor_out  == 8'h00, "gates FF&FF nor");
        `ASSERT(xnor_out == 8'hFF, "gates FF&FF xnor");

        a = 8'h55; b = 8'hAA; #1;
        `ASSERT(and_out == 8'h00, "gates 55&AA and");
        `ASSERT(or_out  == 8'hFF, "gates 55&AA or");
        `ASSERT(xor_out == 8'hFF, "gates 55&AA xor");
        `ASSERT(nand_out == 8'hFF, "gates 55&AA nand");
        `ASSERT(nor_out  == 8'h00, "gates 55&AA nor");
        `ASSERT(xnor_out == 8'h00, "gates 55&AA xnor");

        a = 8'h0F; b = 8'hF0; #1;
        `ASSERT(and_out == 8'h00, "gates 0F&F0 and");
        `ASSERT(or_out  == 8'hFF, "gates 0F&F0 or");
        `ASSERT(xor_out == 8'hFF, "gates 0F&F0 xor");

        // ==================== test adder ====================
        $display("[test_adder]");
        // 0+7=7, 1+6=7, 2+5=7, 3+4=7
        add_a = 4'd0; add_b = 4'd7; add_cin = 1'b0; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd7, "adder 0+7");
        add_a = 4'd1; add_b = 4'd6; add_cin = 1'b0; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd7, "adder 1+6");
        add_a = 4'd2; add_b = 4'd5; add_cin = 1'b0; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd7, "adder 2+5");
        add_a = 4'd3; add_b = 4'd4; add_cin = 1'b0; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd7, "adder 3+4");
        // with carry-in
        add_a = 4'd5; add_b = 4'd3; add_cin = 1'b1; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd9, "adder 5+3+1");
        // overflow
        add_a = 4'd15; add_b = 4'd1; add_cin = 1'b0; #1;
        `ASSERT_EQ({add_cout, add_sum}, 5'd16, "adder 15+1 overflow");

        // ==================== test dff ====================
        $display("[test_dff]");
        rst_n = 1; d = 1; @(posedge clk); #1;
        `ASSERT_EQ(q, 1, "dff posedge capture 1");
        d = 0; @(posedge clk); #1;
        `ASSERT_EQ(q, 0, "dff posedge capture 0");
        @(posedge clk); #1;
        `ASSERT_EQ(q, 0, "dff hold 0");

        // ==================== test counter ====================
        $display("[test_counter]");
        rst_n = 0; @(posedge clk); #1;
        `ASSERT_EQ(cnt_count, 4'd0, "counter async reset");
        `ASSERT(cnt_overflow == 0, "counter overflow after reset");

        rst_n = 1; cnt_enable = 1;
        repeat (1) @(posedge clk); #1;
        `ASSERT_EQ(cnt_count, 4'd1, "counter edge 1");

        repeat (14) @(posedge clk); #1;
        `ASSERT_EQ(cnt_count, 4'd15, "counter edge 15");

        @(posedge clk); #1;
        `ASSERT(cnt_count == 4'd0 && cnt_overflow == 1'b1, "counter overflow");

        // ==================== summary ====================
        if (failures == 0)
            $display("\n=== ALL TESTS PASSED ===");
        else
            $display("\n=== %0d FAILURES ===", failures);
        $finish;
    end

    `undef ASSERT
    `undef ASSERT_EQ

endmodule
