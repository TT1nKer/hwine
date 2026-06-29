// Join: merge N input streams into one output

module spatial_join #(
    parameter DATA_WIDTH = 32,
    parameter NUM_IN     = 2,
    parameter METHOD     = "PRIO"    // "SYNC" or "PRIO"
) (
    input  logic clk,
    input  logic rst_n,

    input  logic [NUM_IN-1:0]                    in_valid,
    input  logic [NUM_IN-1:0][DATA_WIDTH-1:0]    in_data,
    output logic [NUM_IN-1:0]                    in_ready,

    output logic                    out_valid,
    output logic [DATA_WIDTH-1:0]   out_data,
    input  logic                    out_ready
);
    logic [$clog2(NUM_IN):0] sel;

    always_comb begin
        sel = 0;
        for (int j = 0; j < NUM_IN; j++) begin
            if (in_valid[j]) begin
                sel = j;
                j = NUM_IN;  // exit loop
            end
        end
    end

    assign out_valid = |in_valid;
    assign out_data  = in_data[sel];

    genvar i;
    generate
        for (i = 0; i < NUM_IN; i++) begin : g_in_ready
            assign in_ready[i] = (sel == i) && out_ready;
        end
    endgenerate
endmodule
