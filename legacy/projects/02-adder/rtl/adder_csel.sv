// 进位选择加法器 (Carry-Select)
// 思路：分成 4 组，每组同时算两种可能(cin=0, cin=1)，等上组进位到了直接选
// 延迟：组内行波 + 1 级 mux，而不是 16 级

module adder_csel #(parameter N=16) (
    input  logic [N-1:0] a, b,
    input  logic         cin,
    output logic [N-1:0] sum,
    output logic         cout
);
    localparam GROUPS = 4;
    localparam GW = N / GROUPS;  // 4 bits per group

    logic [GROUPS-1:0] group_cout;
    logic [GW-1:0] sum0 [0:GROUPS-1];
    logic [GW-1:0] sum1 [0:GROUPS-1];
    logic         cout0 [0:GROUPS-1];
    logic         cout1 [0:GROUPS-1];

    assign group_cout[0] = cin;

    genvar g;
    generate
        for (g = 0; g < GROUPS; g++) begin : grp
            // 两个并行行波加法器：一个假设进位=0，一个假设进位=1
            assign {cout0[g], sum0[g]}
                = a[g*GW +: GW] + b[g*GW +: GW] + 1'b0;
            assign {cout1[g], sum1[g]}
                = a[g*GW +: GW] + b[g*GW +: GW] + 1'b1;

            // 根据实际进位选择结果
            assign sum[g*GW +: GW] = group_cout[g] ? sum1[g] : sum0[g];

            if (g < GROUPS - 1)
                assign group_cout[g+1] = group_cout[g] ? cout1[g] : cout0[g];
            else
                assign cout = group_cout[g] ? cout1[g] : cout0[g];
        end
    endgenerate
endmodule
