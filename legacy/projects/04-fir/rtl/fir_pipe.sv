// FIR Filter — Fully Pipelined Maximum Parallel
// Pipeline registers after multipliers AND between adder tree levels.
// Latency = 1 (mult reg) + log2(K) (tree) = 4 cycles for K=8. Throughput = 1/cycle.

module fir_pipe #(parameter K=8) (
    input  logic clk, rst_n,
    input  logic        in_valid,
    input  logic [7:0]  in_data,
    output logic        in_ready,
    output logic        out_valid,
    output logic [15:0] out_data,
    input  logic        out_ready
);
    localparam LV = $clog2(K);

    function automatic [7:0] c(input int idx);
        case (idx) 0: c=1; 1: c=2; 2: c=3; 3: c=4;
            4: c=4; 5: c=3; 6: c=2; 7: c=1; default: c=0; endcase
    endfunction

    // Shift register
    logic signed [7:0] s [K];
    // Registered multipliers
    logic signed [15:0] mult [K];
    logic vm;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int j=0; j<K; j++) {s[j], mult[j]} <= 0;
            vm <= 0;
        end else begin
            vm <= in_valid;
            for (int j=K-1; j>0; j--) s[j] <= s[j-1];
            s[0] <= in_valid ? in_data : s[0];
            for (int j=0; j<K; j++)
                mult[j] <= $signed(s[j]) * $signed(c(j));
        end
    end

    // Pipelined adder tree
    logic signed [17:0] l1 [4], l2 [2], l3;
    logic v1, v2, v3;

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int n=0; n<4; n++) l1[n] <= 0;
            v1 <= 0;
        end else begin
            for (int n=0; n<4; n++)
                l1[n] <= mult[2*n] + mult[2*n+1];
            v1 <= vm;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int n=0; n<2; n++) l2[n] <= 0;
            v2 <= 0;
        end else begin
            for (int n=0; n<2; n++)
                l2[n] <= l1[2*n] + l1[2*n+1];
            v2 <= v1;
        end
    end

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            l3 <= 0; v3 <= 0;
        end else begin
            l3 <= l2[0] + l2[1];
            v3 <= v2;
        end
    end

    assign in_ready  = 1'b1;
    assign out_valid = v3;
    assign out_data  = l3[15:0];
endmodule
