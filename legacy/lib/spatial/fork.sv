// Fork: broadcast input to N identical outputs

module spatial_fork #(
    parameter DATA_WIDTH = 32,
    parameter NUM_OUT    = 2
) (
    input  logic clk,
    input  logic rst_n,

    input  logic                    in_valid,
    input  logic [DATA_WIDTH-1:0]   in_data,
    output logic                    in_ready,

    output logic [NUM_OUT-1:0]                   out_valid,
    output logic [NUM_OUT-1:0][DATA_WIDTH-1:0]   out_data,
    input  logic [NUM_OUT-1:0]                   out_ready
);
    assign in_ready = &out_ready;

    genvar i;
    generate
        for (i = 0; i < NUM_OUT; i++) begin : branch
            assign out_valid[i] = in_valid;
            assign out_data[i]  = in_data;
        end
    endgenerate
endmodule
