`timescale 1ns / 1ps

module tb;
    localparam W = 8;
    logic clk, rst_n;
    integer failures = 0;
    always #5 clk = ~clk;

    // Pipe signals
    logic pv_i, pv_o, pr_i, pr_o;
    logic [W-1:0] pd_i, pd_o;
    // Map signals
    logic mv_i, mv_o, mr_i, mr_o;
    logic [W-1:0] ma_i, mb_i, md_o;
    // Reduce signals
    logic rv_i, rv_o, rr_i, rr_o;
    logic [W-1:0] rd_i, rd_o;
    // Fork signals
    logic fv_i, fr_i;
    logic [W-1:0] fd_i;
    logic [1:0] fv_o, fr_o;
    logic [1:0][W-1:0] fd_o;

    spatial_pipe #(.DATA_WIDTH(W), .DEPTH(2)) pipe_dut (
        .clk, .rst_n,
        .in_valid(pv_i), .in_data(pd_i), .in_ready(pr_i),
        .out_valid(pv_o), .out_data(pd_o), .out_ready(pr_o));

    spatial_map #(.DATA_WIDTH(W), .PARALLELISM(1), .FUNC_OP("ADD")) map_dut (
        .clk, .rst_n,
        .in_valid(mv_i), .in_data_a(ma_i), .in_data_b(mb_i), .in_ready(mr_i),
        .out_valid(mv_o), .out_data(md_o), .out_ready(mr_o));

    spatial_reduce #(.DATA_WIDTH(W), .N_ELEMENTS(8), .FUNC_OP("ADD")) red_dut (
        .clk, .rst_n,
        .in_valid(rv_i), .in_data(rd_i), .in_ready(rr_i),
        .out_valid(rv_o), .out_data(rd_o), .out_ready(rr_o));

    spatial_fork #(.DATA_WIDTH(W), .NUM_OUT(2)) fork_dut (
        .clk, .rst_n,
        .in_valid(fv_i), .in_data(fd_i), .in_ready(fr_i),
        .out_valid(fv_o), .out_data(fd_o), .out_ready(fr_o));

    initial begin
        $dumpfile("build/sim.vcd");
        $dumpvars(0, tb);
        clk = 0; rst_n = 0; #40; rst_n = 1; #10;

        test_pipe();
        test_map();
        test_reduce();
        test_fork();

        if (failures == 0) $display("\nALL PASS");
        else $display("\n%d FAILURES", failures);
        $finish;
    end

    task test_pipe();
        pr_o = 1; pv_i = 0;
        @(posedge clk);
        pv_i = 1; pd_i = 8'hA5;
        @(posedge clk);
        pv_i = 0;
        repeat (4) @(posedge clk);
        #1;
        if (pv_o !== 1 || pd_o !== 8'hA5) begin
            failures++; $display("FAIL pipe: v=%b d=%h", pv_o, pd_o);
        end else $display("OK pipe");
    endtask

    task test_map();
        mr_o = 1; mv_i = 0;
        @(posedge clk);
        mv_i = 1; ma_i = 8'd30; mb_i = 8'd12;
        @(posedge clk);
        #1;
        if (mv_o !== 1 || md_o !== 8'd42) begin
            failures++; $display("FAIL map: v=%b d=%d", mv_o, md_o);
        end else $display("OK map");
    endtask

    task test_reduce();
        rr_o = 1;
        for (int i = 1; i <= 8; i++) begin
            rv_i = 1; rd_i = i;
            @(posedge clk);
        end
        rv_i = 0;
        repeat (2) @(posedge clk);
        #1;
        if (rv_o !== 1 || rd_o !== 8'd36) begin
            failures++; $display("FAIL reduce: v=%b d=%d", rv_o, rd_o);
        end else $display("OK reduce");
    endtask

    task test_fork();
        fr_o = 2'b11; fv_i = 0;
        @(posedge clk);
        fv_i = 1; fd_i = 8'h5A;
        #1;
        if (fv_o !== 2'b11 || fd_o[0] !== 8'h5A || fd_o[1] !== 8'h5A) begin
            failures++; $display("FAIL fork: v=%b d0=%h d1=%h", fv_o, fd_o[0], fd_o[1]);
        end else $display("OK fork");
    endtask

endmodule
