// FIR Filter — Parallel (direct form) with K multipliers + adder tree
module fir_parallel #(
    parameter DATA_W = 8, COEFF_W = 8, K = 8
) (
    input  logic clk, rst_n,
    input  logic                     in_valid,
    input  logic [DATA_W-1:0]        in_data,
    output logic                     in_ready,
    output logic                     out_valid,
    output logic [DATA_W+COEFF_W-1:0] out_data,
    input  logic                     out_ready
);
    localparam PROD_W = DATA_W + COEFF_W;
    localparam ACC_W  = DATA_W + COEFF_W + $clog2(K);

    function automatic [COEFF_W-1:0] c(input int idx);
        case (idx)
            0: c=1; 1: c=2; 2: c=3; 3: c=4;
            4: c=4; 5: c=3; 6: c=2; 7: c=1;
            default: c=0;
        endcase
    endfunction

    logic [DATA_W-1:0] shift [K];
    assign in_ready = 1'b1;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int j = 0; j < K; j++) shift[j] <= '0;
            out_valid <= 1'b0;
        end else begin
            out_valid <= in_valid;
            if (in_valid) begin
                for (int j = K-1; j > 0; j--) shift[j] <= shift[j-1];
                shift[0] <= in_data;
            end
        end
    end

    // K multipliers + K-input adder tree
    genvar i, l, n;
    logic [PROD_W-1:0] prod [K];
    generate
        for (i = 0; i < K; i++) begin : tap
            assign prod[i] = $signed(shift[i]) * $signed(c(i));
        end
    endgenerate

    localparam LEVELS = $clog2(K);
    logic [ACC_W-1:0] tree [LEVELS+1] [K];
    generate
        for (n = 0; n < K; n++)
            assign tree[0][n] = ACC_W'(prod[n]);
        for (l = 0; l < LEVELS; l++) begin : level
            localparam int NP = K >> (l+1);
            for (n = 0; n < NP; n++) begin : node
                assign tree[l+1][n] = tree[l][2*n] + tree[l][2*n+1];
            end
        end
    endgenerate

    assign out_data = tree[LEVELS][0][PROD_W-1:0];
endmodule
