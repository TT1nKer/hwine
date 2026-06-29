// 并行前缀加法器 (Brent-Kung tree)
// 核心：进位 = generate 信号的前缀和
//   g_i = a_i & b_i      ← 这一位自己产生进位
//   p_i = a ^ b           ← 这一位能传播进位（实际用异或）
// 组合规则：(g1,p1) ∘ (g0,p0) = (g1 | p1&g0, p1&p0)
// 树状两两组合，log2(N) 级完成

module adder_bk #(parameter N=16) (
    input  logic [N-1:0] a, b,
    input  logic         cin,
    output logic [N-1:0] sum,
    output logic         cout
);
    localparam LEVELS = $clog2(N);

    // Each level stores generate and propagate
    logic [N-1:0] g [0:LEVELS];
    logic [N-1:0] p [0:LEVELS];
    logic [N-1:0] carry_vec;

    // Level 0: initial generate/propagate from inputs
    assign g[0] = a & b;
    assign p[0] = a ^ b;

    // Brent-Kung parallel prefix tree
    // Strategy: build up groups of size 2, 4, 8, ... (2^l)
    genvar l;
    generate
        for (l = 1; l <= LEVELS; l = l + 1) begin : prefix_level
            localparam STEP = 1 << (l - 1);
            genvar i;
            for (i = 0; i < N; i = i + 1) begin : prefix_bit
                if (i >= STEP)
                    assign {g[l][i], p[l][i]} = combine(g[l-1][i], p[l-1][i],
                                                         g[l-1][i-STEP], p[l-1][i-STEP]);
                else
                    assign {g[l][i], p[l][i]} = {g[l-1][i], p[l-1][i]};
            end
        end
    endgenerate

    // Carry vector: carry[i] = generate(0..i) | propagate(0..i) & cin
    // carry[0] is carry INTO bit 1; ... carry[N-1] is cout
    genvar j;
    generate
        for (j = 0; j < N; j = j + 1) begin : carry_gen
            assign carry_vec[j] = g[LEVELS][j] | (p[LEVELS][j] & cin);
        end
    endgenerate

    // Sum: p[0][i] ^ (carry INTO bit i)
    // carry INTO bit 0 = cin
    // carry INTO bit i (i>0) = carry_vec[i-1]
    assign sum   = p[0] ^ {carry_vec[N-2:0], cin};
    assign cout  = carry_vec[N-1];

    // ---- prefix combine function (for assignments only) ----
    function automatic logic [1:0] combine(
        input logic g1, p1, g0, p0
    );
        // (g1, p1) o (g0, p0) = (g1 | p1 & g0, p1 & p0)
        combine = {g1 | (p1 & g0), p1 & p0};
    endfunction

endmodule
