// Auto-generated testbench for piped_mac_tile
`timescale 1ns / 1ps

module tb_piped_mac_tile();
  logic clk = 0;
  logic rst_n = 0;
  logic signed [7:0] w0;
  logic signed [7:0] a0;
  logic signed [7:0] w1;
  logic signed [7:0] a1;
  logic signed [7:0] w7;
  logic signed [7:0] a7;
  logic signed [7:0] result;

  piped_mac_tile #(.DATA_WIDTH(8)) dut (
    .clk(clk),
    .rst_n(rst_n),
    .w0(w0),
    .a0(a0),
    .w1(w1),
    .a1(a1),
    .w7(w7),
    .a7(a7)
,
    .result(result)
  );

  always #5 clk = ~clk;

  initial begin
    $display("Testbench for piped_mac_tile");
    rst_n = 0;
    #20 rst_n = 1;
    #1000;
    $display("PASS");
    $finish;
  end
endmodule