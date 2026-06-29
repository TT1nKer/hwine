// FIR Filter — Serial MAC, one tap per cycle
module fir_serial #(parameter K=8) (
    input  logic clk, rst_n,
    input  logic        in_valid,
    input  logic [7:0]  in_data,
    output logic        in_ready,
    output logic        out_valid,
    output logic [15:0] out_data,
    input  logic        out_ready
);
    logic signed [7:0] s [K];
    logic signed [18:0] acc;
    logic [3:0] tap;  // 0=idle, 1..K=tap index

    assign in_ready = (tap == 0);

    always_ff @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            for (int j=0; j<K; j++) s[j] <= 0;
            acc <= 0; tap <= 0; out_valid <= 0;
        end else begin
            if (out_valid && out_ready)
                out_valid <= 0;

            if (in_valid && in_ready) begin
                for (int j=K-1; j>0; j--) s[j] <= s[j-1];
                s[0] <= in_data;
                acc <= 0;
                tap <= 1;
            end

            if (tap > 0 && tap <= K) begin
                // Accumulate one product
                case (tap)
                    1: acc <= acc + $signed(s[0]) * 1;
                    2: acc <= acc + $signed(s[1]) * 2;
                    3: acc <= acc + $signed(s[2]) * 3;
                    4: acc <= acc + $signed(s[3]) * 4;
                    5: acc <= acc + $signed(s[4]) * 4;
                    6: acc <= acc + $signed(s[5]) * 3;
                    7: acc <= acc + $signed(s[6]) * 2;
                    8: begin
                        acc <= acc + $signed(s[7]) * 1;
                        out_data <= 16'(acc + $signed(s[7]) * 1);
                        out_valid <= 1;
                    end
                endcase
                if (tap == K)
                    tap <= 0;
                else
                    tap <= tap + 1;
            end
        end
    end
endmodule
