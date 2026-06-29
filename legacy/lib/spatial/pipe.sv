// Pipe: registered FIFO with valid/ready handshake

module spatial_pipe #(
    parameter DATA_WIDTH = 32,
    parameter DEPTH      = 2
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
    if (DEPTH == 0) begin : wire_thru
        assign out_valid = in_valid;
        assign out_data  = in_data;
        assign in_ready  = out_ready;
    end else begin : fifo
        logic [DATA_WIDTH-1:0] mem [DEPTH];
        logic [$clog2(DEPTH):0] wr_ptr, rd_ptr, count;

        assign in_ready = (count < DEPTH);

        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                wr_ptr <= '0;
                rd_ptr <= '0;
                count  <= '0;
                out_valid <= 1'b0;
            end else begin
                if (in_valid && in_ready) begin
                    mem[wr_ptr] <= in_data;
                    wr_ptr <= wr_ptr + 1;
                    if (wr_ptr == DEPTH - 1)
                        wr_ptr <= '0;
                end

                if (out_valid && out_ready && !(in_valid && in_ready))
                    count <= count - 1;
                else if (!(out_valid && out_ready) && in_valid && in_ready)
                    count <= count + 1;

                if (count > 0 || (in_valid && in_ready)) begin
                    out_data  <= mem[rd_ptr];
                    out_valid <= 1'b1;
                    if (out_ready || !out_valid) begin
                        rd_ptr <= rd_ptr + 1;
                        if (rd_ptr == DEPTH - 1)
                            rd_ptr <= '0;
                    end
                end else begin
                    out_valid <= 1'b0;
                end
            end
        end
    end
endmodule
