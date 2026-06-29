`timescale 1ns/1ps
module tmp_tb;
    logic clk=0, rst_n=0;
    logic iv, ov, ir, ora;
    logic [7:0] id;
    logic [15:0] od;
    integer err=0;
    always #5 clk=~clk;

    fir_pipe dut(.clk,.rst_n,.in_valid(iv),.in_data(id),.in_ready(ir),
                 .out_valid(ov),.out_data(od),.out_ready(ora));

    initial begin
        $dumpfile("build/sim.vcd"); $dumpvars(0,tmp_tb);
        #40 rst_n=1; #10 ora=1;

        for (int i=0; i<8; i++) begin
            id = (i*37)%256;
            iv = 1; @(posedge clk); iv = 0;
            repeat(10) @(posedge clk);
            if (ov) $display("out[%0d] = %0d", i, $signed(od));
            else $display("out[%0d] = timeout", i);
        end
        $finish;
    end
endmodule
