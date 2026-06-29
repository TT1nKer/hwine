`timescale 1ns / 1ps

// Smoke test with minimal parameters to verify logic correctness
module tb_smoke;
    localparam LANES     = 4;
    localparam TILE_O    = 2;
    localparam LANES_PER_O = LANES / TILE_O;
    localparam ACC_WIDTH = 32;

    localparam AW = LANES_PER_O * 8;
    localparam WW = LANES * 4;
    localparam OW = TILE_O * ACC_WIDTH;

    logic clk, rst_n;
    integer failures;
    integer passes;

    always #5 clk = ~clk;

    logic                       in_valid;
    logic [AW-1:0]              in_a_data;
    logic [WW-1:0]              in_w_data;
    logic                       in_last;
    logic                       in_ready;

    logic                       out_valid;
    logic [OW-1:0]              out_data;
    logic                       out_ready;

    dot_int4_tile #(
        .LANES(LANES), .TILE_O(TILE_O), .ACC_WIDTH(ACC_WIDTH)
    ) dut (
        .clk, .rst_n,
        .in_valid, .in_a_data, .in_w_data, .in_last, .in_ready,
        .out_valid, .out_data, .out_ready
    );

    function logic signed [ACC_WIDTH-1:0] out_ch;
        input integer ch;
        begin
            out_ch = $signed(out_data[ch * ACC_WIDTH +: ACC_WIDTH]);
        end
    endfunction

    task wait_ready;
    begin
        while (!in_ready) @(posedge clk);
    end
    endtask

    task wait_valid;
    begin
        while (!out_valid) @(posedge clk);
    end
    endtask

    initial begin
        integer k, o;
        integer expected0, expected1;
        $dumpfile("build/smoke.vcd");
        $dumpvars(0, tb_smoke);

        clk = 0; rst_n = 0; in_valid = 0; out_ready = 0;
        failures = 0; passes = 0;
        #40; rst_n = 1; #10;

        // Test 1: Single cycle (TILE_K=2, LANES_PER_O=2)
        // Weights: ch0=[1,2], ch1=[-3,4], Activations: [10, -5]
        // Expected: ch0 = 1*10 + 2*(-5) = 0, ch1 = (-3)*10 + 4*(-5) = -50
        $display("=== Test 1: Single cycle ===");
        wait_ready();

        // Use NBA to avoid race with DUT's always_ff
        in_a_data <= {-8'sd5, 8'sd10};
        in_w_data <= {4'sd4, -4'sd3, 4'sd2, 4'sd1};
        in_valid  <= 1;
        in_last   <= 1;
        @(posedge clk);
        in_valid <= 0;
        out_ready <= 1;

        wait_valid();
        expected0 = 0;
        expected1 = -50;
        if ($signed(out_ch(0)) !== expected0) begin
            failures = failures + 1;
            $display("FAIL ch0: got %0d, exp %0d", $signed(out_ch(0)), expected0);
        end else passes = passes + 1;
        if ($signed(out_ch(1)) !== expected1) begin
            failures = failures + 1;
            $display("FAIL ch1: got %0d, exp %0d", $signed(out_ch(1)), expected1);
        end else passes = passes + 1;
        @(posedge clk);
        out_ready <= 0;

        // Test 2: Multi-cycle (TILE_K=4, 2 cycles)
        // Weights ch0=[1,2,3,4], ch1=[-4,-3,-2,-1]
        // Activations=[1,1,1,1]
        // Expected: ch0=10, ch1=-10
        $display("=== Test 2: Multi-cycle ===");
        wait_ready();

        // Cycle 1: a=[1,1], ch0=[1,2], ch1=[-4,-3]
        in_a_data <= {8'sd1, 8'sd1};
        in_w_data <= {-4'sd3, -4'sd4, 4'sd2, 4'sd1};
        in_valid  <= 1;
        in_last   <= 0;
        @(posedge clk);

        // Cycle 2: a=[1,1], ch0=[3,4], ch1=[-2,-1]
        in_a_data <= {8'sd1, 8'sd1};
        in_w_data <= {-4'sd1, -4'sd2, 4'sd4, 4'sd3};
        in_last   <= 1;
        @(posedge clk);
        in_valid  <= 0;
        out_ready <= 1;

        wait_valid();
        expected0 = 10;
        expected1 = -10;
        if ($signed(out_ch(0)) !== expected0) begin
            failures = failures + 1;
            $display("FAIL ch0: got %0d, exp %0d", $signed(out_ch(0)), expected0);
        end else passes = passes + 1;
        if ($signed(out_ch(1)) !== expected1) begin
            failures = failures + 1;
            $display("FAIL ch1: got %0d, exp %0d", $signed(out_ch(1)), expected1);
        end else passes = passes + 1;
        @(posedge clk);
        out_ready <= 0;

        // Test 3: Back-to-back
        $display("=== Test 3: Back-to-back ===");
        wait_ready();
        in_a_data <= {8'sd2, 8'sd3};
        in_w_data <= {4'sd1, 4'sd1, 4'sd1, 4'sd1};
        in_valid  <= 1;
        in_last   <= 1;
        @(posedge clk);
        in_valid  <= 0;
        out_ready <= 1;

        wait_valid();
        expected0 = 5; expected1 = 5;
        if ($signed(out_ch(0)) !== expected0) begin
            failures = failures + 1;
            $display("FAIL ch0: got %0d, exp %0d", $signed(out_ch(0)), expected0);
        end else passes = passes + 1;
        if ($signed(out_ch(1)) !== expected1) begin
            failures = failures + 1;
            $display("FAIL ch1: got %0d, exp %0d", $signed(out_ch(1)), expected1);
        end else passes = passes + 1;
        @(posedge clk);
        out_ready <= 0;

        if (failures == 0)
            $display("\nSMOKE ALL PASS (%0d checks)", passes);
        else
            $display("\nSMOKE %0d FAIL, %0d PASS", failures, passes);
        $finish;
    end

endmodule
