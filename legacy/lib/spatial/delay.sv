// Delay: pure shift register of DEPTH stages

module spatial_delay #(
    parameter DATA_WIDTH = 32,
    parameter DEPTH      = 4
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
    logic [DATA_WIDTH-1:0] shift [DEPTH];
    logic [DEPTH-1:0]      valid_pipe;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            valid_pipe <= '0;
        end else begin
            valid_pipe <= {valid_pipe[DEPTH-2:0], in_valid};
            if (in_valid)
                shift[0] <= in_data;
            for (int j = 0; j < DEPTH-1; j++)
                shift[j+1] <= shift[j];
        end
    end

    assign out_valid = valid_pipe[DEPTH-1];
    assign out_data  = shift[DEPTH-1];
    assign in_ready  = 1'b1;
endmodule
