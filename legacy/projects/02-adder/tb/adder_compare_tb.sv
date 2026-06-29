`timescale 1ns / 1ps

module tb;
    logic [15:0] a, b;
    logic        cin;
    logic [15:0] sum_rc, sum_csel, sum_bk;
    logic        cout_rc, cout_csel, cout_bk;

    integer failures = 0;

    adder_rc   dut_rc  (a, b, cin, sum_rc,   cout_rc);
    adder_csel dut_csel(a, b, cin, sum_csel, cout_csel);
    adder_bk   dut_bk  (a, b, cin, sum_bk,   cout_bk);

    initial begin
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);

        for (int i = 0; i < 5000; i++) begin
            a = $urandom % 65536;
            b = $urandom % 65536;
            cin = $urandom % 2;
            #1;

            // 三个加法器结果必须一致
            if ({cout_rc, sum_rc} !== {cout_csel, sum_csel}) begin
                failures++;
                $display("FAIL [RC vs CSEL] %0d+%0d+%0d: rc=%0d csel=%0d",
                         a, b, cin, {cout_rc, sum_rc}, {cout_csel, sum_csel});
            end
            if ({cout_rc, sum_rc} !== {cout_bk, sum_bk}) begin
                failures++;
                $display("FAIL [RC vs BK] %0d+%0d+%0d: rc=%0d bk=%0d",
                         a, b, cin, {cout_rc, sum_rc}, {cout_bk, sum_bk});
            end
        end

        if (failures == 0)
            $display("\n=== ALL TESTS PASSED (3 adders, 5000 cases each) ===");
        else
            $display("\n=== %0d FAILURES ===", failures);
        $finish;
    end

endmodule
