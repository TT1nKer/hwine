// Map: apply function f to element pairs, with configurable parallelism.
// p=1: single instance. p>1: round-robin dispatch to p instances, ordered output.

module spatial_map #(
    parameter DATA_WIDTH  = 32,
    parameter PARALLELISM = 1,
    parameter FUNC_OP     = "ADD"
) (
    input  logic clk,
    input  logic rst_n,

    input  logic                    in_valid,
    input  logic [DATA_WIDTH-1:0]   in_data_a,
    input  logic [DATA_WIDTH-1:0]   in_data_b,
    output logic                    in_ready,

    output logic                    out_valid,
    output logic [DATA_WIDTH-1:0]   out_data,
    input  logic                    out_ready
);
    if (PARALLELISM == 1) begin : single
        logic [DATA_WIDTH-1:0] res;
        always_comb begin
            if (FUNC_OP == "ADD") res = in_data_a + in_data_b;
            else res = in_data_a;
        end
        assign out_data  = res;
        assign out_valid = in_valid;
        assign in_ready  = out_ready;

    end else begin : multi
        localparam IDX_W = $clog2(PARALLELISM);
        logic [IDX_W-1:0] wr_idx, rd_idx;
        logic [PARALLELISM-1:0] busy, done;
        logic [PARALLELISM-1:0][DATA_WIDTH-1:0] a_r, b_r, r_r;

        // Static mux for input ready
        logic [IDX_W-1:0] wr_enc;
        always_comb begin
            wr_enc = '0;
            for (int j = 0; j < PARALLELISM; j++) begin
                if (!busy[j]) begin wr_enc = j; break; end
            end
        end
        assign in_ready = !busy[wr_idx];

        // Static mux for output
        assign out_data  = r_r[rd_idx];
        assign out_valid = done[rd_idx];

        always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) begin
                wr_idx <= '0;
                rd_idx <= '0;
                busy   <= '0;
                done   <= '0;
            end else begin
                if (in_valid && in_ready) begin
                    a_r[wr_idx] <= in_data_a;
                    b_r[wr_idx] <= in_data_b;
                    busy[wr_idx] <= 1'b1;
                    wr_idx <= wr_idx + 1;
                end
                if (done[rd_idx] && out_ready) begin
                    busy[rd_idx] <= 1'b0;
                    done[rd_idx] <= 1'b0;
                    rd_idx <= rd_idx + 1;
                end
            end
        end

        genvar i;
        for (i = 0; i < PARALLELISM; i++) begin : inst
            always_comb begin
                if (FUNC_OP == "ADD") r_r[i] = a_r[i] + b_r[i];
                else r_r[i] = a_r[i];
            end

            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n)
                    done[i] <= 1'b0;
                else if (busy[i] && !done[i])
                    done[i] <= 1'b1;
                else if (done[i] && out_ready && rd_idx == i)
                    done[i] <= 1'b0;
            end
        end
    end
endmodule
