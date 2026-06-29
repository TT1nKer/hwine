`timescale 1ns / 1ps

module tb;
    logic [15:0] a, b;
    logic        cin;
    logic [15:0] sum;
    logic        cout;

    integer failures = 0;
    integer i;

    adder16 dut (.*);

    initial begin
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);

        // --- directed tests ---
        $display("[test_zero]");
        a = 0; b = 0; cin = 0; #1;
        assert_result(17'd0);

        $display("[test_ones]");
        a = 16'hFFFF; b = 16'hFFFF; cin = 0; #1;
        assert_result(17'd131070);   // 0xFFFF + 0xFFFF = 0x1FFFE

        a = 16'hFFFF; b = 16'hFFFF; cin = 1; #1;
        assert_result(17'd131071);   // 0xFFFF + 0xFFFF + 1 = 0x1FFFF

        $display("[test_carry_chain]");
        a = 16'h0001; b = 16'h0001; cin = 0; #1;
        assert_result(17'd2);

        a = 16'h8000; b = 16'h8000; cin = 0; #1;
        assert_result(17'd65536);  // cout=1, sum=0

        $display("[test_random]");
        for (i = 0; i < 1000; i++) begin
            a = $urandom % 65536;
            b = $urandom % 65536;
            cin = $urandom % 2;
            #1;
            assert_result(a + b + cin);
        end

        if (failures == 0)
            $display("\n=== ALL TESTS PASSED ===");
        else
            $display("\n=== %0d FAILURES ===", failures);
        $finish;
    end

    task assert_result(input [16:0] expected);
        if ({cout, sum} !== expected) begin
            failures++;
            $display("FAIL %0d + %0d + %0d: got %0d, expected %0d",
                     a, b, cin, {cout, sum}, expected);
        end
    endtask

endmodule
