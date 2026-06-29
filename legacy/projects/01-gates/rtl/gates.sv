// Combinational gates: AND, OR, XOR, NAND, NOR, XNOR
module gates (
    input  logic [7:0] a,
    input  logic [7:0] b,
    output logic [7:0] and_out,
    output logic [7:0] or_out,
    output logic [7:0] xor_out,
    output logic [7:0] nand_out,
    output logic [7:0] nor_out,
    output logic [7:0] xnor_out
);

    assign and_out  = a & b;
    assign or_out   = a | b;
    assign xor_out  = a ^ b;
    assign nand_out = ~(a & b);
    assign nor_out  = ~(a | b);
    assign xnor_out = ~(a ^ b);

endmodule


// 4-bit full adder
module adder #(
    parameter WIDTH = 4
) (
    input  logic [WIDTH-1:0] a,
    input  logic [WIDTH-1:0] b,
    input  logic             cin,
    output logic [WIDTH-1:0] sum,
    output logic             cout
);

    logic [WIDTH:0] result;
    assign result = a + b + cin;
    assign sum    = result[WIDTH-1:0];
    assign cout   = result[WIDTH];

endmodule


// D flip-flop with async reset
module dff (
    input  logic clk,
    input  logic rst_n,
    input  logic d,
    output logic q
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) q <= 1'b0;
        else        q <= d;
    end

endmodule


// 4-bit counter with enable and overflow
module counter #(
    parameter WIDTH = 4
) (
    input  logic             clk,
    input  logic             rst_n,
    input  logic             enable,
    output logic [WIDTH-1:0] count,
    output logic             overflow
);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            count    <= '0;
            overflow <= 1'b0;
        end else if (enable) begin
            {overflow, count} <= count + 1'b1;
        end
    end

endmodule
