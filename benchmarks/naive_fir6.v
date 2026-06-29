// Naive 6-tap FIR: serial MAC chain (baseline, unoptimized)
module naive_fir6(input [11:0] In_X, output [28:0] Out_Y);
  // 6 coefficients (same as ex1EP16): random example values
  wire signed [28:0] p1 = In_X * 12'd100;
  wire signed [28:0] p2 = In_X * 12'd200;
  wire signed [28:0] p3 = In_X * 12'd300;
  wire signed [28:0] p4 = In_X * 12'd400;
  wire signed [28:0] p5 = In_X * 12'd500;
  wire signed [28:0] p6 = In_X * 12'd600;
  wire signed [28:0] s1 = p1 + p2;
  wire signed [28:0] s2 = s1 + p3;
  wire signed [28:0] s3 = s2 + p4;
  wire signed [28:0] s4 = s3 + p5;
  assign Out_Y = s4 + p6;
endmodule
