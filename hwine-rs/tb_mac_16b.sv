`timescale 1ns / 1ps
module tb_mac_16b;
  logic signed [15:0] a0 = 0;
  logic signed [15:0] w0 = 0;
  logic signed [15:0] a1 = 0;
  logic signed [15:0] w1 = 0;
  logic signed [15:0] a2 = 0;
  logic signed [15:0] w2 = 0;
  logic signed [15:0] a3 = 0;
  logic signed [15:0] w3 = 0;
  logic signed [15:0] a4 = 0;
  logic signed [15:0] w4 = 0;
  logic signed [15:0] a5 = 0;
  logic signed [15:0] w5 = 0;
  logic signed [15:0] a6 = 0;
  logic signed [15:0] w6 = 0;
  logic signed [15:0] a7 = 0;
  logic signed [15:0] w7 = 0;
  logic signed [15:0] a8 = 0;
  logic signed [15:0] w8 = 0;
  logic signed [15:0] a9 = 0;
  logic signed [15:0] w9 = 0;
  logic signed [15:0] a10 = 0;
  logic signed [15:0] w10 = 0;
  logic signed [15:0] a11 = 0;
  logic signed [15:0] w11 = 0;
  logic signed [15:0] a12 = 0;
  logic signed [15:0] w12 = 0;
  logic signed [15:0] a13 = 0;
  logic signed [15:0] w13 = 0;
  logic signed [15:0] a14 = 0;
  logic signed [15:0] w14 = 0;
  logic signed [15:0] a15 = 0;
  logic signed [15:0] w15 = 0;
  logic signed [15:0] result;
  mac_tile_16_16b dut(.*);

  integer errors = 0, t = 0;
  initial begin
    $dumpfile("mac_16b.vcd");
    $dumpvars(0, tb_mac_16b);
    // Test 0: expected = -17
    a0 = 10; w0 = -3;
    a1 = -2; w1 = -4;
    a2 = 12; w2 = 0;
    a3 = 1; w3 = -1;
    a4 = -16; w4 = -1;
    a5 = -6; w5 = -2;
    a6 = 11; w6 = -3;
    a7 = 5; w7 = -3;
    a8 = 1; w8 = 2;
    a9 = -7; w9 = -4;
    a10 = -3; w10 = -4;
    a11 = 5; w11 = -3;
    a12 = -10; w12 = -1;
    a13 = -11; w13 = -1;
    a14 = 8; w14 = -4;
    a15 = -10; w15 = -1;
    #10;
    if (result !== -17) begin
      $display("FAIL test0: expected=%d got=%d", -17, result);
      errors = errors + 1;
    end
    t = t + 1;
    // Test 1: expected = -13
    a0 = -2; w0 = 1;
    a1 = -10; w1 = 1;
    a2 = 8; w2 = 0;
    a3 = 1; w3 = -4;
    a4 = 13; w4 = 3;
    a5 = 7; w5 = -3;
    a6 = -6; w6 = 2;
    a7 = 7; w7 = -3;
    a8 = 6; w8 = 0;
    a9 = -3; w9 = 1;
    a10 = 1; w10 = -1;
    a11 = -12; w11 = -3;
    a12 = -6; w12 = -4;
    a13 = -1; w13 = -1;
    a14 = -6; w14 = 0;
    a15 = 13; w15 = -3;
    #10;
    if (result !== -13) begin
      $display("FAIL test1: expected=%d got=%d", -13, result);
      errors = errors + 1;
    end
    t = t + 1;
    // Test 2: expected = -29
    a0 = 13; w0 = 2;
    a1 = -7; w1 = 0;
    a2 = 0; w2 = -1;
    a3 = -8; w3 = 1;
    a4 = -1; w4 = -4;
    a5 = 0; w5 = -1;
    a6 = 11; w6 = -4;
    a7 = 9; w7 = 1;
    a8 = 7; w8 = 2;
    a9 = -2; w9 = 0;
    a10 = -8; w10 = -3;
    a11 = 15; w11 = -1;
    a12 = -11; w12 = 1;
    a13 = -13; w13 = -1;
    a14 = -9; w14 = 3;
    a15 = -7; w15 = 2;
    #10;
    if (result !== -29) begin
      $display("FAIL test2: expected=%d got=%d", -29, result);
      errors = errors + 1;
    end
    t = t + 1;
    // Test 3: expected = -53
    a0 = -16; w0 = -2;
    a1 = 0; w1 = 2;
    a2 = -5; w2 = -3;
    a3 = -10; w3 = 2;
    a4 = 3; w4 = 2;
    a5 = -4; w5 = 3;
    a6 = -7; w6 = 0;
    a7 = 7; w7 = -4;
    a8 = -6; w8 = -3;
    a9 = -16; w9 = 0;
    a10 = 4; w10 = 1;
    a11 = 15; w11 = -3;
    a12 = -15; w12 = 0;
    a13 = -9; w13 = 2;
    a14 = 7; w14 = -2;
    a15 = 3; w15 = 3;
    #10;
    if (result !== -53) begin
      $display("FAIL test3: expected=%d got=%d", -53, result);
      errors = errors + 1;
    end
    t = t + 1;
    // Test 4: expected = -89
    a0 = 9; w0 = -1;
    a1 = 7; w1 = -4;
    a2 = 12; w2 = -1;
    a3 = 12; w3 = -3;
    a4 = -9; w4 = -3;
    a5 = -1; w5 = 3;
    a6 = -2; w6 = -3;
    a7 = -12; w7 = -2;
    a8 = 5; w8 = -2;
    a9 = -15; w9 = 3;
    a10 = -2; w10 = -2;
    a11 = -2; w11 = 0;
    a12 = -16; w12 = 2;
    a13 = -12; w13 = -1;
    a14 = -13; w14 = -1;
    a15 = -2; w15 = 0;
    #10;
    if (result !== -89) begin
      $display("FAIL test4: expected=%d got=%d", -89, result);
      errors = errors + 1;
    end
    t = t + 1;
    $display("tests=%0d errors=%0d", t, errors);
    if (errors == 0) $display("PASS"); else $display("FAIL");
    $finish;
  end
endmodule