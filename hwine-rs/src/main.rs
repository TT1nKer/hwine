use hwine_rs::cost::ExtractMode;
use hwine_rs::egraph::EGraph;
use hwine_rs::ir::DataType;
use hwine_rs::ir::{AtomOp, ENode};
use hwine_rs::rtl::generate_rtl;
use std::fs;
use std::time::Instant;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        usage();
        return;
    }
    match args[1].as_str() {
        "bench" => bench(&args),
        "rtl" => rtl_gen(&args),
        "synth" => synth(&args),
        "scan" => scan(&args),
        "compare" => compare(&args),
        "softmax" => softmax(&args),
        "interactive" => interactive(),
        _ => usage(),
    }
}

fn usage() {
    eprintln!("hwine — FPGA structural discovery via e-graph");
    eprintln!("  hwine bench <N> <add|mac|full> [--bidir] [--loose] [--narrow K]");
    eprintln!("  hwine rtl   <N> [output.sv] [--bidir] [--loose]");
    eprintln!("  hwine synth <N> <add|mac> [--bidir] [--loose]");
    eprintln!("  hwine scan  <N>");
    eprintln!("  hwine compare <N>");
    eprintln!("  hwine interactive");
}

// --- Config ---

struct Config {
    bidir: bool,
    loose: bool,
    narrow: usize,
}
impl Default for Config {
    fn default() -> Self {
        Self {
            bidir: false,
            loose: false,
            narrow: 8,
        }
    }
}
impl Config {
    fn parse(args: &[String]) -> Self {
        let mut c = Self::default();
        let mut i = 0;
        while i < args.len() {
            match &args[i][..] {
                "--bidir" => c.bidir = true,
                "--loose" => c.loose = true,
                "--narrow" => {
                    c.narrow = args.get(i + 1).and_then(|s| s.parse().ok()).unwrap_or(8);
                    i += 1;
                }
                _ => {}
            }
            i += 1;
        }
        c
    }
}

// --- Build helpers ---

fn build_add_chain(eg: &mut EGraph, n: usize) -> u32 {
    let mut vs = Vec::with_capacity(n);
    for i in 0..n {
        vs.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }
    let mut c = vs[0];
    for i in 1..n {
        c = eg.add(ENode::new(AtomOp::Add, vec![c, vs[i]], DataType::default()));
    }
    c
}

fn build_mac_chain(eg: &mut EGraph, n: usize, full: bool) -> u32 {
    let mut ws = Vec::with_capacity(n);
    let mut ag = Vec::with_capacity(n);
    for i in 0..n {
        ws.push(eg.add(ENode::leaf(AtomOp::Var(i * 2))));
        ag.push(eg.add(ENode::leaf(AtomOp::Var(i * 2 + 1))));
    }
    if full {
        let z = eg.add(ENode::leaf(AtomOp::Zero));
        let ai = eg.add(ENode::new(AtomOp::AccInit, vec![z], DataType::default()));
        let mut acc = ai;
        let mut mc = ai;
        for i in 0..n {
            let m = eg.add(ENode::new(
                AtomOp::Mul,
                vec![ws[i], ag[i]],
                DataType::default(),
            ));
            acc = eg.add(ENode::new(
                AtomOp::AccStep,
                vec![acc, m],
                DataType::default(),
            ));
            mc = eg.add(ENode::new(
                AtomOp::Mac,
                vec![ws[i], ag[i], mc],
                DataType::default(),
            ));
        }
        eg.union(acc, mc);
        eg.canon(acc)
    } else {
        let mut muls = Vec::with_capacity(n);
        for i in 0..n {
            muls.push(eg.add(ENode::new(
                AtomOp::Mul,
                vec![ws[i], ag[i]],
                DataType::default(),
            )));
        }
        let mut c = muls[0];
        for i in 1..n {
            c = eg.add(ENode::new(
                AtomOp::Add,
                vec![c, muls[i]],
                DataType::default(),
            ));
        }
        c
    }
}

fn saturate(eg: &mut EGraph, cfg: &Config) -> usize {
    let nl = if cfg.loose { 30 } else { 10 };
    let sl = if cfg.loose { 20 } else { cfg.narrow };
    eg.saturate_with_config(50, 30000, nl, sl, cfg.bidir)
}

fn tree_depth(node: &ENode, eg: &EGraph) -> usize {
    if node.children.is_empty() {
        return 0;
    }
    1 + node
        .children
        .iter()
        .map(|&c| tree_depth(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
        .max()
        .unwrap_or(0)
}

fn add_delay(n: usize) -> f64 {
    (n.saturating_sub(1)) as f64 * 0.8
}
fn mac_delay(n: usize) -> f64 {
    2.5 + add_delay(n)
}

// --- bench ---

fn bench(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let mode = args.get(3).map(|s| &s[..]).unwrap_or("add");
    let cfg = Config::parse(&args[4..].to_vec());

    let t0 = Instant::now();
    let mut eg = EGraph::new();

    let (cid, ser_ns, label) = match mode {
        "add" => (
            build_add_chain(&mut eg, n),
            add_delay(n),
            format!("ADD N={n}"),
        ),
        "mac" => (
            build_mac_chain(&mut eg, n, false),
            mac_delay(n),
            format!("MAC N={n}"),
        ),
        "full" => (
            build_mac_chain(&mut eg, n, true),
            mac_delay(n),
            format!("FULL N={n}"),
        ),
        _ => return,
    };

    let iters = saturate(&mut eg, &cfg);
    let dt = t0.elapsed();
    let (best, _) = eg.extract_optimal(cid, ExtractMode::MinDelay);
    let td = tree_depth(&best, &eg);
    let sp = ser_ns / (td as f64 * 0.8).max(0.01);

    println!(
        "{label}: {iters}it {}cls {}un {:.3}s  ser={ser_ns:.1}ns tree={}lv({:.1}ns) {sp:.1}x  [bidir={},loose={},narrow={}]",
        eg.n_classes(),
        eg.union_count(),
        dt.as_secs_f64(),
        td,
        td as f64 * 0.8,
        cfg.bidir,
        cfg.loose,
        cfg.narrow
    );
}

// --- rtl ---

fn rtl_gen(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let cfg = Config::parse(&args[3..].to_vec());
    let output = if args.len() > 3 && !args[3].starts_with("--") {
        &args[3]
    } else {
        "output.sv"
    };

    let t0 = Instant::now();
    let mut eg = EGraph::new();
    let cid = build_mac_chain(&mut eg, n, false);
    let iters = saturate(&mut eg, &cfg);
    println!(
        "Saturated: {iters}it {}cls {:.3}s",
        eg.n_classes(),
        t0.elapsed().as_secs_f64()
    );

    let (best, _) = eg.extract_optimal(cid, ExtractMode::MinDelay);
    println!("Tree depth: {} levels", tree_depth(&best, &eg));

    let rtl = generate_rtl(&eg, cid, &format!("mac_tile_{n}"), 16);
    fs::write(output, &rtl).unwrap();
    println!("RTL: {} lines -> {output}", rtl.lines().count());
    println!("Total: {:.3}s", t0.elapsed().as_secs_f64());
}

// --- synth (generate serial + tree RTL) ---

fn synth(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let mode = args.get(3).map(|s| &s[..]).unwrap_or("add");
    let cfg = Config::parse(&args[4..].to_vec());

    // Serial (no saturation)
    let mut eg_s = EGraph::new();
    let cid_s = if mode == "mac" {
        build_mac_chain(&mut eg_s, n, false)
    } else {
        build_add_chain(&mut eg_s, n)
    };
    let rtl_s = generate_rtl(&eg_s, cid_s, &format!("serial_{mode}_{n}"), 16);
    let (best_s, _) = eg_s.extract_optimal(cid_s, ExtractMode::MinDelay);
    let sd = tree_depth(&best_s, &eg_s);

    // Tree (with saturation)
    let mut eg_t = EGraph::new();
    let cid_t = if mode == "mac" {
        build_mac_chain(&mut eg_t, n, false)
    } else {
        build_add_chain(&mut eg_t, n)
    };
    saturate(&mut eg_t, &cfg);
    let rtl_t = generate_rtl(&eg_t, cid_t, &format!("tree_{mode}_{n}"), 16);
    let (best_t, _) = eg_t.extract_optimal(cid_t, ExtractMode::MinDelay);
    let td = tree_depth(&best_t, &eg_t);

    // Write files
    let sf = format!("serial_{mode}_{n}.sv");
    let tf = format!("tree_{mode}_{n}.sv");
    fs::write(&sf, &rtl_s).unwrap();
    fs::write(&tf, &rtl_t).unwrap();

    let sp = sd as f64 / td.max(1) as f64;
    println!("{mode} N={n}: RTL generation only; following delay numbers are heuristic estimates.");
    println!(
        "  {sf:30} {} lines, {} levels (estimated {:.1}ns)",
        rtl_s.lines().count(),
        sd,
        sd as f64 * 0.8
    );
    println!(
        "  {tf:30} {} lines, {} levels (estimated {:.1}ns), {sp:.1}x depth ratio",
        rtl_t.lines().count(),
        td,
        td as f64 * 0.8
    );
    println!("  Yosys: yosys -p \"read_verilog -sv {sf}; synth -top serial_{mode}_{n}; stat\"");
    println!("  Yosys: yosys -p \"read_verilog -sv {tf}; synth -top tree_{mode}_{n}; stat\"");
}

// --- scan ---

fn scan(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let mut eg = EGraph::new();
    let mut vs = Vec::with_capacity(n);
    for i in 0..n {
        vs.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }
    let mut chain = eg.add(ENode::new(
        AtomOp::Scan,
        vec![vs[0], vs[1]],
        DataType::default(),
    ));
    for i in 2..n {
        chain = eg.add(ENode::new(
            AtomOp::Scan,
            vec![chain, vs[i]],
            DataType::default(),
        ));
    }
    let t0 = Instant::now();
    let iters = eg.saturate(50, 30000);
    let dt = t0.elapsed();
    let (best, _) = eg.extract_optimal(chain, ExtractMode::MinDelay);
    let sd = n - 1;
    let td = tree_depth(&best, &eg);
    let sp = sd as f64 / td.max(1) as f64;
    println!(
        "SCAN N={n}: {iters}it {}cls {:.3}s  ser={}lv tree={td}lv {sp:.1}x",
        eg.n_classes(),
        dt.as_secs_f64(),
        sd
    );
}

// --- compare ---

fn compare(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let configs = [
        ("default", Config::default()),
        (
            "bidir",
            Config {
                bidir: true,
                ..Default::default()
            },
        ),
        (
            "loose",
            Config {
                loose: true,
                narrow: 20,
                ..Default::default()
            },
        ),
        (
            "bidir+loose",
            Config {
                bidir: true,
                loose: true,
                narrow: 20,
            },
        ),
    ];
    println!("ADD N={n} — Configuration comparison:");
    println!(
        "  {:<20} {:>8} {:>6} {:>8} {:>6} {:>8}",
        "config", "time", "cls", "unions", "depth", "speedup"
    );
    for (name, cfg) in &configs {
        let mut eg = EGraph::new();
        let cid = build_add_chain(&mut eg, n);
        let t0 = Instant::now();
        let _iters = saturate(&mut eg, cfg);
        let dt = t0.elapsed();
        let (best, _) = eg.extract_optimal(cid, ExtractMode::MinDelay);
        let td = tree_depth(&best, &eg);
        let sp = add_delay(n) / (td as f64 * 0.8).max(0.01);
        println!(
            "  {name:<20} {:8.3} {:>6} {:>8} {:>6} {:>7.1}x",
            dt.as_secs_f64(),
            eg.n_classes(),
            eg.union_count(),
            td,
            sp
        );
    }
}

// --- softmax ---

fn softmax(args: &[String]) {
    let n: usize = args.get(2).and_then(|s| s.parse().ok()).unwrap_or(8);
    let cfg = Config::parse(&args[3..].to_vec());

    let mut eg = EGraph::new();
    // Build a vector of N variables: a hypothetical input vector
    let mut vs = Vec::with_capacity(n);
    for i in 0..n {
        vs.push(eg.add(ENode::leaf(AtomOp::Var(i))));
    }

    // Build: SOFTMAX applied to the whole vector
    // Softmax: RTL not yet supported (requires Exp/Div ops)
    let softmax_node = eg.add(ENode::new(
        AtomOp::Softmax,
        vec![vs[0]],
        DataType::default(),
    ));

    let t0 = Instant::now();
    let iters = saturate(&mut eg, &cfg);
    let dt = t0.elapsed();

    let cid = eg.canon(softmax_node);
    let cls = eg.class_nodes(cid).unwrap();
    println!(
        "Softmax N={n}: {iters}it {}cls {:.3}s",
        eg.n_classes(),
        dt.as_secs_f64()
    );
    println!("  {} equivalent representations found:", cls.len());

    for node in cls.iter().take(10) {
        let d = 1 + node
            .children
            .iter()
            .map(|&c| tree_depth_rec(&eg.extract_optimal(c, ExtractMode::MinDelay).0, &eg))
            .max()
            .unwrap_or(0);
        println!("    depth={:2}  {:?}", d, node.op);
    }
}

fn tree_depth_rec(node: &ENode, eg: &EGraph) -> usize {
    if node.children.is_empty() {
        return 0;
    }
    1 + node
        .children
        .iter()
        .map(|&c| tree_depth_rec(&eg.extract_optimal(c, ExtractMode::MinDelay).0, eg))
        .max()
        .unwrap_or(0)
}

// --- interactive ---

fn interactive() {
    use std::io::Write;
    println!("hwine interactive — type commands:");
    println!("  bench <N> <add|mac|full> [--bidir] [--loose]");
    println!("  synth <N> <add|mac> [--bidir] [--loose]");
    println!("  scan <N>");
    println!("  compare <N>");
    println!("  quit");
    let stdin = std::io::stdin();
    let mut line = String::new();
    loop {
        line.clear();
        print!("> ");
        std::io::stdout().flush().unwrap();
        stdin.read_line(&mut line).unwrap();
        let parts: Vec<String> = line
            .trim()
            .split_whitespace()
            .map(|s| s.to_string())
            .collect();
        if parts.is_empty() {
            continue;
        }
        let mut full = vec!["hwine".to_string()];
        full.extend(parts.iter().cloned());
        match full[1].as_str() {
            "quit" | "exit" | "q" => break,
            "bench" => bench(&full),
            "scan" => scan(&full),
            "synth" => synth(&full),
            "compare" => compare(&full),
            "softmax" => softmax(&full),
            _ => println!("unknown: {}", full[1]),
        }
    }
}
