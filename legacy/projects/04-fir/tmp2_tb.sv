`timescale 1ns/1ps
module tmp2_tb;
    logic clk=0, rst_n=0;
    logic iv, ov, ir, ora;
    logic [7:0] id;
    logic [15:0] od;
    always #5 clk=~clk;
    fir_pipe dut(.clk,.rst_n,.in_valid(iv),.in_data(id),.in_ready(ir),
                 .out_valid(ov),.out_data(od),.out_ready(ora));
    initial begin
        $dumpfile("build/sim.vcd"); $dumpvars(0,tmp2_tb);
        $monitor("%0t iv=%b id=%0d ov=%b od=%0d v0=%b v1=%b v2=%b prod0=%0d l1_0=%0d l2_0=%0d l3=%0d",
                 $time, iv, id, ov, $signed(od),
                 dut.v0, dut.v1, dut.v2,
                 $signed(dut.prod[0]), $signed(dut.l1[0]),
                 $signed(dut.l2[0]), $signed(dut.l3));
        #40 rst_n=1; #10 ora=1;
        id=42; iv=1; @(posedge clk); iv=0;
        repeat(8) @(posedge clk);
        $finish;
    end
endmodule
