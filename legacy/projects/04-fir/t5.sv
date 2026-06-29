`timescale 1ns/1ps
module t5;
    logic clk=0, rst_n=0, iv=0, ov, ora=1;
    logic [7:0] id=0;
    logic [15:0] od;
    integer i, err=0;
    always #5 clk=~clk;

    fir_pipe dut(.clk,.rst_n,.in_valid(iv),.in_data(id),.in_ready(),
                 .out_valid(ov),.out_data(od),.out_ready(ora));

    // Reference
    logic signed [7:0] rs [8];
    function [7:0] rc(input int idx);
        case (idx) 0: rc=1; 1: rc=2; 2: rc=3; 3: rc=4;
            4: rc=4; 5: rc=3; 6: rc=2; 7: rc=1; default: rc=0; endcase
    endfunction

    initial begin
        $dumpfile("build/sim.vcd"); $dumpvars(0,t5);
        for (int j=0; j<8; j++) rs[j]=0;
        #40 rst_n=1; #10;

        for (i=0; i<20; i++) begin
            // Feed
            id = (i*17+3) % 256;
            iv <= 1; @(posedge clk); iv <= 0;

            // Shift reference
            for (int j=7; j>0; j--) rs[j] = rs[j-1];
            rs[0] = id;

            // Wait for output (pipeline depth = 4)
            repeat(6) @(posedge clk);
            if (ov && i>=7) begin  // first 7 samples: pipeline filling
                logic [15:0] exp = 0;
                for (int j=0; j<8; j++) exp += rs[j] * rc(j);
                if ($signed(od) != $signed(exp)) begin
                    err++; $display("FAIL[%0d]: got %0d exp %0d",i,$signed(od),$signed(exp));
                end
            end
        end

        if (err==0) $display("PASS: pipelined FIR OK");
        else $display("FAIL: %0d errors", err);
        $finish;
    end
endmodule
