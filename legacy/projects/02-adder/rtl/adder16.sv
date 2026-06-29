module adder16 (
    input  logic [15:0] a,
    input  logic [15:0] b,
    input  logic        cin,
    output logic [15:0] sum,
    output logic        cout
);
    logic [16:0] result;
    assign result = a + b + {16'b0, cin};
    assign sum    = result[15:0];
    assign cout   = result[16];
endmodule
