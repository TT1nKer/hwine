`timescale 1ns / 1ps

module tb_dbg;
    localparam LANES     = 4;
    localparam TILE_O    = 2;
    localparam LANES_PER_O = LANES / TILE_O;
    localparam ACC_WIDTH = 32;
    localparam AW = LANES_PER_O * 8;
    localparam WW = LANES * 4;

    logic clk, rst_n;
    logic                       in_valid;
    logic [AW-1:0]              in_a_data;
    logic [WW-1:0]              in_w_data;
    logic                       in_last;
    logic                       in_ready;
    logic                       out_valid;
    logic                       out_ready;

    always #5 clk = ~clk;

    dot_int4_tile #(.LANES(LANES), .TILE_O(TILE_O), .ACC_WIDTH(ACC_WIDTH)) dut (
        .clk, .rst_n, .in_valid, .in_a_data, .in_w_data, .in_last, .in_ready,
        .out_valid, .out_data(), .out_ready
    );

    initial begin
        $dumpfile("build/dbg.vcd");
        $dumpvars(0, tb_dbg);
        clk = 0; rst_n = 0; in_valid = 0; out_ready = 0;
        #40;
        $display("t=%0t: before rst_n=1, in_ready=%b", $time, in_ready);
        rst_n = 1;
        #5;
        $display("t=%0t: after rst_n=1, in_ready=%b", $time, in_ready);
        #5;
        $display("t=%0t: +10ns, in_ready=%b, in_valid=%b", $time, in_ready, in_valid);
        #10;
        $display("t=%0t: +20ns, in_ready=%b", $time, in_ready);

        // Try to send a minimal transaction
        while (!in_ready) @(posedge clk);
        $display("t=%0t: in_ready=1, sending data", $time);

        in_a_data = {8'd5, 8'd10};
        in_w_data = {4'd1, 4'd1, 4'd1, 4'd1};
        in_valid = 1;
        in_last  = 1;
        @(posedge clk);
        $display("t=%0t: posedge after send, out_valid=%b", $time, out_valid);
        in_valid = 0;
        out_ready = 1;

        #5;
        $display("t=%0t: +5ns, out_valid=%b", $time, out_valid);
        #5;
        $display("t=%0t: +10ns, out_valid=%b", $time, out_valid);
        #10;
        $display("t=%0t: +20ns, out_valid=%b", $time, out_valid);

        #100;
        $display("t=%0t: done", $time);
        $finish;
    end
endmodule
