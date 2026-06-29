// DotInt4Tile: int4 weight × int8 activation MAC array
// y[TILE_O] = W[TILE_O, TILE_K] · x[TILE_K]
//
// LANES total MAC units, partitioned across TILE_O output channels.
// Each output channel has LANES_PER_O = LANES/TILE_O MACs computing in parallel.
// TILE_K determines cycle count; in_last signals final accumulation step.

module dot_int4_tile #(
    parameter LANES     = 128,
    parameter TILE_O    = 32,
    parameter ACC_WIDTH = 32
) (
    input  logic clk,
    input  logic rst_n,

    input  logic                              in_valid,
    input  logic [(LANES/TILE_O)*8-1:0]       in_a_data,
    input  logic [LANES*4-1:0]                in_w_data,
    input  logic                              in_last,
    output logic                              in_ready,

    output logic                              out_valid,
    output logic [TILE_O*ACC_WIDTH-1:0]       out_data,
    input  logic                              out_ready
);

    localparam LANES_PER_O = LANES / TILE_O;

    logic [TILE_O-1:0][ACC_WIDTH-1:0] acc;
    logic [TILE_O-1:0][ACC_WIDTH-1:0] result_r;
    logic result_valid;

    logic [TILE_O-1:0][ACC_WIDTH-1:0] sum_prod;

    typedef enum logic [1:0] {IDLE, COMPUTE, OUTPUT} state_t;
    state_t state, state_next;

    assign in_ready = !result_valid;

    assign out_valid = result_valid;
    assign out_data  = result_r;

    // FSM state register + result_valid
    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state <= IDLE;
            result_valid <= 1'b0;
        end else begin
            state <= state_next;

            if (state == OUTPUT && out_ready)
                result_valid <= 1'b0;
            else if ((state == IDLE || state == COMPUTE) && in_valid && in_ready && in_last)
                result_valid <= 1'b1;
        end
    end

    // FSM next state
    always_comb begin
        state_next = state;
        case (state)
            IDLE: begin
                if (in_valid && in_last && in_ready)
                    state_next = OUTPUT;
                else if (in_valid)
                    state_next = COMPUTE;
            end
            COMPUTE: begin
                if (in_valid && in_last && in_ready)
                    state_next = OUTPUT;
            end
            OUTPUT: begin
                if (out_ready)
                    state_next = IDLE;
            end
        endcase
    end

    // Combinational: sum of LANES_PER_O products per output channel
    generate
        genvar o;
        for (o = 0; o < TILE_O; o++) begin : out_chan
            always_comb begin
                logic signed [ACC_WIDTH-1:0] tmp;
                integer l;
                tmp = '0;
                for (l = 0; l < LANES_PER_O; l++) begin
                    tmp = tmp
                        + $signed(in_w_data[(o * LANES_PER_O + l)*4 +: 4])
                        * $signed(in_a_data[l*8 +: 8]);
                end
                sum_prod[o] = tmp;
            end

            // Sequential: accumulator and output latch
            always_ff @(posedge clk or negedge rst_n) begin
                if (!rst_n) begin
                    acc[o]      <= '0;
                    result_r[o] <= '0;
                end else begin
                    if (state == OUTPUT && out_ready)
                        acc[o] <= '0;

                    if ((state == IDLE || state == COMPUTE) && in_valid && in_ready) begin
                        if (state == IDLE)
                            acc[o] <= sum_prod[o];
                        else
                            acc[o] <= acc[o] + sum_prod[o];
                    end

                    if ((state == IDLE || state == COMPUTE) && in_valid && in_ready && in_last) begin
                        if (state == IDLE)
                            result_r[o] <= sum_prod[o];
                        else
                            result_r[o] <= acc[o] + sum_prod[o];
                    end
                end
            end
        end
    endgenerate

endmodule
