use crate::ir::AtomOp;

/// FPGA cost model — calibrated for Xilinx 7-series

pub fn lut_cost(op: AtomOp) -> f64 {
    match op {
        AtomOp::Add => 0.5,
        AtomOp::Mul | AtomOp::Mac | AtomOp::DspMul | AtomOp::DspMac | AtomOp::Madd => 0.0, // DSP
        AtomOp::Shl | AtomOp::Shr | AtomOp::Pack | AtomOp::Unpack | AtomOp::Concat
        | AtomOp::Slice | AtomOp::Extract | AtomOp::Broadcast => 0.0, // wiring
        AtomOp::Sat | AtomOp::Round => 1.0,
        AtomOp::ReduceAdd | AtomOp::ReduceMax | AtomOp::ReduceMin => 0.5,
        AtomOp::Scan => 2.0,
        AtomOp::Buffer => 0.0, // FF
        AtomOp::Route => 0.0,
        AtomOp::Pipe | AtomOp::Delay => 0.0, // FF
        AtomOp::Quant | AtomOp::Dequant | AtomOp::DequantW => 1.0,
        AtomOp::Sub => 0.5,
        AtomOp::Div => 4.0,
        AtomOp::Exp => 4.0,
        AtomOp::Softmax => 8.0,
        AtomOp::Const(_) | AtomOp::Var(_) | AtomOp::StrLit | AtomOp::Zero | AtomOp::One => 0.0,
        AtomOp::AccInit | AtomOp::AccStep => 1.0,
        AtomOp::AccRead | AtomOp::AccReset => 0.0,
    }
}

pub fn dsp_cost(op: AtomOp) -> f64 {
    match op {
        AtomOp::Mul | AtomOp::Mac | AtomOp::Madd | AtomOp::DspMul | AtomOp::DspMac => 1.0,
        _ => 0.0,
    }
}

pub fn ff_cost(op: AtomOp) -> f64 {
    match op {
        AtomOp::Pipe | AtomOp::AccInit => 8.0,
        AtomOp::Delay => 8.0,
        AtomOp::AccStep => 16.0,
        AtomOp::Buffer => 16.0,
        _ => 0.0,
    }
}

/// Critical path delay in nanoseconds
pub fn delay_ns(op: AtomOp) -> f64 {
    match op {
        AtomOp::Add => 0.8,
        AtomOp::Mul | AtomOp::Mac | AtomOp::Madd | AtomOp::DspMul | AtomOp::DspMac => 2.5,
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
    }
}

/// Pipeline cycle latency
pub fn cycle_latency(op: AtomOp) -> usize {
    match op {
        AtomOp::Pipe | AtomOp::Delay | AtomOp::AccStep => 1,
        AtomOp::Buffer => 2,
        _ => 0,
    }
}

/// FPGA cost summary
#[derive(Debug, Clone)]
pub struct FpgaStats {
    pub lut: f64,
    pub dsp: f64,
    pub ff: f64,
    pub delay_ns: f64,
    pub cycles: usize,
    pub fmax_mhz: f64,
}

impl FpgaStats {
    pub fn for_node(op: AtomOp, child_stats: &[FpgaStats]) -> Self {
        let child_lut: f64 = child_stats.iter().map(|s| s.lut).sum();
        let child_dsp: f64 = child_stats.iter().map(|s| s.dsp).sum();
        let child_ff: f64 = child_stats.iter().map(|s| s.ff).sum();
        let max_child_delay: f64 = child_stats.iter().map(|s| s.delay_ns).fold(0.0, f64::max);
        let max_child_cycles: usize = child_stats.iter().map(|s| s.cycles).max().unwrap_or(0);

        let delay = delay_ns(op) + max_child_delay;
        let fmax = if delay > 0.0 { (1000.0 / delay).min(500.0) } else { 500.0 };

        Self {
            lut: lut_cost(op) + child_lut,
            dsp: dsp_cost(op) + child_dsp,
            ff: ff_cost(op) + child_ff,
            delay_ns: delay,
            cycles: cycle_latency(op) + max_child_cycles,
            fmax_mhz: fmax,
        }
    }

    pub fn empty() -> Self {
        Self { lut: 0.0, dsp: 0.0, ff: 0.0, delay_ns: 0.0, cycles: 0, fmax_mhz: 500.0 }
    }
}
