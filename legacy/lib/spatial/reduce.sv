// Reduce: accumulator-based reduction of N elements.

module spatial_reduce #(
    parameter DATA_WIDTH  = 32,
    parameter N_ELEMENTS   = 8,
    parameter FUNC_OP      = "ADD"
) (
    input  logic clk,
    input  logic rst_n,

    input  logic                    in_valid,
    input  logic [DATA_WIDTH-1:0]   in_data,
    output logic                    in_ready,

    output logic                    out_valid,
    output logic [DATA_WIDTH-1:0]   out_data,
    input  logic                    out_ready
);
    logic [DATA_WIDTH-1:0]  acc;
    logic [$clog2(N_ELEMENTS):0] count;
    logic done;

    assign in_ready  = 1'b1;
    assign out_valid = done;
    assign out_data  = acc;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc   <= '0;
            count <= '0;
            done  <= 1'b0;
        end else begin
            if (in_valid) begin
                if (FUNC_OP == "ADD")
                    acc <= acc + in_data;
                else
                    acc <= in_data;

                if (count == N_ELEMENTS - 1) begin
                    count <= '0;
                    done  <= 1'b1;
                end else begin
                    count <= count + 1;
                end
            end else if (done && out_ready) begin
                done <= 1'b0;
            end
        end
    end
endmodule
