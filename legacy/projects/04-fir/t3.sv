`timescale 1ns/1ps
module t3;
    logic clk=0, rst_n=0, iv, ov, ir, ora;
    logic [7:0] id;
    logic [15:0] od;
    always #5 clk=~clk;
    fir_pipe dut(.clk,.rst_n,.in_valid(iv),.in_data(id),.in_ready(ir),
                 .out_valid(ov),.out_data(od),.out_ready(ora));
    initial begin
        $dumpfile("build/sim.vcd"); $dumpvars(0,t3);
        #40 rst_n=1; #10 ora=1;
        id=42; iv=1; @(posedge clk); iv=0;
        repeat(5) @(posedge clk);
        $display("final: ov=%b od=%0d", ov, $signed(od));
        $finish;
    end
endmodule
