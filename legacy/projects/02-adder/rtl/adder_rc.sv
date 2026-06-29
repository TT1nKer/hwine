// 行波进位加法器 (Ripple-Carry)
// 每 1 位算完，进位传给下一位——像多米诺骨牌
module adder_rc #(parameter N=16) (
    input  logic [N-1:0] a, b,
    input  logic         cin,
    output logic [N-1:0] sum,
    output logic         cout
);
    logic [N:0] c;
    assign c[0] = cin;

    genvar i;
    generate
        for (i = 0; i < N; i++) begin
            assign sum[i] = a[i] ^ b[i] ^ c[i];     // sum = a xor b xor carry
            assign c[i+1] = (a[i] & b[i]) | (a[i] & c[i]) | (b[i] & c[i]);  // carry out
        end
    endgenerate

    assign cout = c[N];
endmodule
