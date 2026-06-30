use crate::ir::{AtomOp, ENode, DataType};

/// FPGA cost model — calibrated for Xilinx 7-series, width-aware

/// Width scaling factor: cost multiplier relative to 16-bit baseline
fn width_scale(dtype: &DataType) -> f64 {
    (dtype.width as f64 / 16.0).max(0.25)
}

pub fn lut_cost(op: AtomOp, dtype: &DataType) -> f64 {
    let base = match op {
        AtomOp::Add => 0.5,
        AtomOp::Mul | AtomOp::Mac | AtomOp::DspMul | AtomOp::DspMac | AtomOp::DspPreAdd | AtomOp::Madd => 0.0, // DSP
        AtomOp::Shl | AtomOp::Shr | AtomOp::Pack | AtomOp::Unpack | AtomOp::Concat
        | AtomOp::Slice | AtomOp::Extract | AtomOp::Broadcast => 0.0, // wiring
        AtomOp::Sat | AtomOp::Round => 1.0,
        AtomOp::ReduceAdd | AtomOp::ReduceMax | AtomOp::ReduceMin => 0.5,
        AtomOp::Scan => 2.0,
        AtomOp::Buffer => 0.0,
        AtomOp::Route => 0.0,
        AtomOp::Pipe | AtomOp::Delay => 0.0,
        AtomOp::Quant | AtomOp::Dequant | AtomOp::DequantW => 1.0,
        AtomOp::Sub => 0.5,
        AtomOp::Div => 4.0,
        AtomOp::Exp => 4.0,
        AtomOp::Softmax => 8.0,
        AtomOp::Const(_) | AtomOp::Var(_) | AtomOp::StrLit | AtomOp::Zero | AtomOp::One => 0.0,
        AtomOp::AccInit | AtomOp::AccStep => 1.0,
        AtomOp::AccRead | AtomOp::AccReset => 0.0,
        AtomOp::StreamRead => 0.0,
        AtomOp::StreamWrite => 0.0,
        AtomOp::StreamFifo => 0.0, // pipeline register (no LUT)
    };
    // Width scaling for arithmetic ops only
    if op.is_arithmetic() { base * width_scale(dtype) } else { base }
}

pub fn dsp_cost(op: AtomOp, dtype: &DataType) -> f64 {
    let base = match op {
        AtomOp::Mul | AtomOp::Mac | AtomOp::Madd | AtomOp::DspMul | AtomOp::DspMac | AtomOp::DspPreAdd => {
            // Wide multipliers may use multiple DSP slices
            if dtype.width > 25 { (dtype.width as f64 / 25.0).ceil()  } else { 1.0 }
        }
        _ => 0.0,
    };
    base
}

pub fn ff_cost(op: AtomOp, dtype: &DataType) -> f64 {
    let bits = dtype.width as f64;
    match op {
        AtomOp::Pipe | AtomOp::AccInit => bits,
        AtomOp::Delay => bits,
        AtomOp::AccStep => bits * 2.0,
        AtomOp::Buffer => bits * 2.0,
        AtomOp::StreamFifo => bits,  // pipeline register: one FF per bit
        _ => 0.0,
    }
}

/// Critical path delay in nanoseconds (width-aware: wider adders have longer CARRY4 chains)
pub fn delay_ns(op: AtomOp, dtype: &DataType) -> f64 {
    let base = match op {
        AtomOp::Add => 0.8,
        AtomOp::Mul | AtomOp::Mac | AtomOp::Madd | AtomOp::DspMul | AtomOp::DspMac | AtomOp::DspPreAdd => 2.5,
        AtomOp::Shl | AtomOp::Shr | AtomOp::Pack | AtomOp::Unpack | AtomOp::Concat
        | AtomOp::Slice | AtomOp::Extract => 0.3,
        AtomOp::Sat | AtomOp::Round => 0.8,
        AtomOp::ReduceAdd | AtomOp::ReduceMax | AtomOp::ReduceMin => 0.8,
        AtomOp::Scan => 1.5,
        AtomOp::Sub => 0.8,
        AtomOp::Div => 3.0,
        AtomOp::Exp => 3.0,
        AtomOp::Softmax => 5.0,
        AtomOp::Buffer | AtomOp::Pipe | AtomOp::Delay => 0.3,
        AtomOp::Route => 1.2,
        AtomOp::Broadcast => 0.8,
        AtomOp::Quant | AtomOp::Dequant | AtomOp::DequantW => 1.0,
        AtomOp::Const(_) | AtomOp::Var(_) | AtomOp::StrLit | AtomOp::Zero | AtomOp::One => 0.0,
        AtomOp::AccInit | AtomOp::AccStep => 1.0,
        AtomOp::AccRead | AtomOp::AccReset => 0.3,
        AtomOp::StreamRead | AtomOp::StreamWrite | AtomOp::StreamFifo => 0.3,
    };
    // Width scaling: wider ops have longer carry chains
    if op == AtomOp::Add || op == AtomOp::Sub || op == AtomOp::ReduceAdd {
        base + (dtype.width as f64 / 64.0) * 0.4 // 64-bit add adds ~0.4ns
    } else {
        base
    }
}

/// Pipeline cycle latency
pub fn cycle_latency(op: AtomOp) -> usize {
    match op {
        AtomOp::Pipe | AtomOp::Delay | AtomOp::AccStep | AtomOp::StreamFifo => 1,
        AtomOp::Buffer => 2,
        _ => 0,
    }
}

/// FPGA cost summary — multi-objective resource vector
#[derive(Debug, Clone, PartialEq)]
pub struct FpgaStats {
    pub lut: f64,
    pub dsp: f64,
    pub ff: f64,
    pub delay_ns: f64,
    pub cycles: usize,
    pub fmax_mhz: f64,
}

/// Multi-objective extraction mode
#[derive(Debug, Clone, Copy)]
pub enum ExtractMode {
    /// Minimize critical-path delay
    MinDelay,
    /// Minimize LUT usage under max_delay_ns constraint
    MinLut { max_delay_ns: f64 },
    /// Minimize DSP usage under max_delay_ns constraint
    MinDsp { max_delay_ns: f64 },
    /// Minimize FF usage under max_delay_ns constraint
    MinFf { max_delay_ns: f64 },
    /// Weighted sum: w_delay*delay + w_lut*lut + w_dsp*dsp + w_ff*ff
    Weighted { w_delay: f64, w_lut: f64, w_dsp: f64, w_ff: f64 },
    /// Pareto frontier: return all non-dominated alternatives
    Pareto,
}

impl FpgaStats {
    pub fn for_node(op: AtomOp, child_stats: &[FpgaStats], dtype: &DataType) -> Self {
        let child_lut: f64 = child_stats.iter().map(|s| s.lut).sum();
        let child_dsp: f64 = child_stats.iter().map(|s| s.dsp).sum();
        let child_ff: f64 = child_stats.iter().map(|s| s.ff).sum();
        let max_child_delay: f64 = child_stats.iter().map(|s| s.delay_ns).fold(0.0, f64::max);
        let max_child_cycles: usize = child_stats.iter().map(|s| s.cycles).max().unwrap_or(0);

        // Pipeline registers reset delay: children's combinational paths are
        // captured by the register, so output delay = register clk-to-q only.
        let is_pipeline_barrier = matches!(op, AtomOp::Pipe | AtomOp::StreamFifo | AtomOp::AccInit);
        let prev_delay = if is_pipeline_barrier { 0.0 } else { max_child_delay };
        let delay = delay_ns(op, dtype) + prev_delay;
        let fmax = if delay > 0.0 { (1000.0 / delay).min(500.0) } else { 500.0 };

        Self {
            lut: lut_cost(op, dtype) + child_lut,
            dsp: dsp_cost(op, dtype) + child_dsp,
            ff: ff_cost(op, dtype) + child_ff,
            delay_ns: delay,
            cycles: cycle_latency(op) + max_child_cycles,
            fmax_mhz: fmax,
        }
    }

    pub fn empty() -> Self {
        Self { lut: 0.0, dsp: 0.0, ff: 0.0, delay_ns: 0.0, cycles: 0, fmax_mhz: 500.0 }
    }

    pub fn infinite() -> Self {
        Self { lut: 1e10, dsp: 1e10, ff: 1e10, delay_ns: 1e10, cycles: 0, fmax_mhz: 0.0 }
    }

    /// Returns true if `self` dominates `other` (better or equal in all dimensions, strictly better in at least one).
    /// Includes cycle latency for pipeline-aware Pareto frontiers.
    ///
    /// # Examples
    ///
    /// ```
    /// use hwine_rs::cost::FpgaStats;
    /// let a = FpgaStats { lut: 5.0, dsp: 1.0, ff: 10.0, delay_ns: 3.0, cycles: 2, fmax_mhz: 333.0 };
    /// let b = FpgaStats { lut: 6.0, dsp: 2.0, ff: 12.0, delay_ns: 3.0, cycles: 3, fmax_mhz: 333.0 };
    /// assert!(a.dominates(&b));   // a is strictly better in LUT/DSP/FF/cycles
    /// assert!(!b.dominates(&a));  // b is worse in all dimensions
    /// ```
    pub fn dominates(&self, other: &FpgaStats) -> bool {
        let not_worse = self.lut <= other.lut
            && self.dsp <= other.dsp
            && self.ff <= other.ff
            && self.delay_ns <= other.delay_ns
            && self.cycles <= other.cycles;
        let strictly_better = self.lut < other.lut
            || self.dsp < other.dsp
            || self.ff < other.ff
            || self.delay_ns < other.delay_ns
            || self.cycles < other.cycles;
        not_worse && strictly_better
    }

    /// Computes a scalar cost for single-objective ranking.
    /// Returns f64::INFINITY if constraints are violated.
    pub fn scalar_cost(&self, mode: ExtractMode) -> f64 {
        match mode {
            ExtractMode::MinDelay => self.delay_ns,
            ExtractMode::MinLut { max_delay_ns } => {
                if self.delay_ns > max_delay_ns { f64::INFINITY }
                else { self.lut + self.delay_ns * 0.001 } // slight delay tiebreaker
            }
            ExtractMode::MinDsp { max_delay_ns } => {
                if self.delay_ns > max_delay_ns { f64::INFINITY }
                else { self.dsp + self.delay_ns * 0.001 }
            }
            ExtractMode::MinFf { max_delay_ns } => {
                if self.delay_ns > max_delay_ns { f64::INFINITY }
                else { self.ff + self.delay_ns * 0.001 }
            }
            ExtractMode::Weighted { w_delay, w_lut, w_dsp, w_ff } => {
                w_delay * self.delay_ns + w_lut * self.lut + w_dsp * self.dsp + w_ff * self.ff
            }
            ExtractMode::Pareto => self.delay_ns * self.lut.max(1.0) * self.dsp.max(1.0).ln(), // fallback scalar for memo
        }
    }

    /// Filter a list of (node, stats) to keep only Pareto-optimal (non-dominated) entries.
    /// Deduplicates identical stats.
    pub fn pareto_filter(candidates: Vec<(ENode, FpgaStats)>) -> Vec<(ENode, FpgaStats)> {
        let mut result: Vec<(ENode, FpgaStats)> = Vec::new();
        let mut seen: Vec<FpgaStats> = Vec::new();
        for cand in candidates {
            // Skip duplicates
            if seen.iter().any(|s| s == &cand.1) { continue; }
            seen.push(cand.1.clone());
            // Skip if dominated by an existing result
            if result.iter().any(|(_, s)| s.dominates(&cand.1)) {
                continue;
            }
            // Remove results dominated by this candidate
            result.retain(|(_, s)| !cand.1.dominates(s));
            result.push(cand);
        }
        result
    }
}
