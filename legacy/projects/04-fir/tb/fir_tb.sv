`timescale 1ns / 1ps

module tb;
    localparam DATA_W = 8, COEFF_W = 8, K = 8;
    localparam FULL_W = DATA_W + COEFF_W + $clog2(K);

    logic clk, rst_n;
    integer failures = 0, pass = 0;
    always #5 clk = ~clk;

    logic s_in_v, s_in_r, s_out_v, s_out_r;
    logic [DATA_W-1:0] s_in_d;
    logic [DATA_W+COEFF_W-1:0] s_out_d;

    logic p_in_v, p_in_r, p_out_v, p_out_r;
    logic [DATA_W-1:0] p_in_d;
    logic [DATA_W+COEFF_W-1:0] p_out_d;

    fir_serial #(.K(K)) serial_dut (
        .clk, .rst_n, .in_valid(s_in_v), .in_data(s_in_d), .in_ready(s_in_r),
        .out_valid(s_out_v), .out_data(s_out_d), .out_ready(s_out_r));

    fir_parallel #(.DATA_W(DATA_W), .COEFF_W(COEFF_W), .K(K)) parallel_dut (
        .clk, .rst_n, .in_valid(p_in_v), .in_data(p_in_d), .in_ready(p_in_r),
        .out_valid(p_out_v), .out_data(p_out_d), .out_ready(p_out_r));

    // Reference model
    logic signed [DATA_W-1:0]  rshift [K];
    logic signed [COEFF_W-1:0] rcoef [K];

    initial begin : test
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);
        clk = 0; rst_n = 0;

        rcoef[0]=1; rcoef[1]=2; rcoef[2]=3; rcoef[3]=4;
        rcoef[4]=4; rcoef[5]=3; rcoef[6]=2; rcoef[7]=1;
        for (int j = 0; j < K; j++) rshift[j] = 0;

        #40; rst_n = 1; #10;

        s_out_r = 1; s_in_v = 0;
        p_out_r = 1; p_in_v = 0;

        for (int i = 0; i < 16; i++) begin
            logic signed [DATA_W-1:0] sample;
            logic signed [FULL_W-1:0] expected;
            logic signed [DATA_W+COEFF_W-1:0] exp_trunc;
            integer jj;

            sample = (i * 37) % 256;

            // Reference: shift in, compute
            for (jj = K-1; jj > 0; jj--) rshift[jj] = rshift[jj-1];
            rshift[0] = sample;
            expected = 0;
            for (jj = 0; jj < K; jj++)
                expected = expected + rshift[jj] * rcoef[jj];
            exp_trunc = expected[DATA_W+COEFF_W-1:0];

            // Feed serial
            @(posedge clk);
            while (!s_in_r) @(posedge clk);
            s_in_v = 1; s_in_d = sample;
            @(posedge clk);
            s_in_v = 0;

            // Wait for serial result (up to 30 cycles)
            for (int w = 0; w < 30; w++) begin
                @(posedge clk);
                if (s_out_v) begin
                    if ($signed(s_out_d) !== $signed(exp_trunc)) begin
                        failures++;
                        $display("FAIL serial[%0d]: got %0d, exp %0d",
                                 i, $signed(s_out_d), $signed(exp_trunc));
                    end else pass++;
                    break;
                end
            end

            // Feed parallel
            p_in_v = 1; p_in_d = sample;
            @(posedge clk);
            p_in_v = 0;

            // Wait for parallel result
            for (int w = 0; w < 10; w++) begin
                @(posedge clk);
                if (p_out_v) begin
                    if ($signed(p_out_d) !== $signed(exp_trunc)) begin
                        failures++;
                        $display("FAIL parallel[%0d]: got %0d, exp %0d",
                                 i, $signed(p_out_d), $signed(exp_trunc));
                    end else pass++;
                    break;
                end
            end
        end

        if (failures == 0)
            $display("\nALL PASS (%0d)", pass);
        else
            $display("\n%0d FAIL, %0d PASS", failures, pass);
        $finish;
    end

endmodule
