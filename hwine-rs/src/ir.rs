use std::fmt;

/// Atom operation codes — data-level primitives for quantization hardware
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum AtomOp {
    // Data compute
    Mul,
    Add,
    Mac,
    Madd,
    Shl,
    Shr,
    Sat,
    Round,

    // Reduction
    ReduceAdd,
    ReduceMax,
    ReduceMin,

    // Prefix scan
    Scan,

    // Data layout
    Pack,
    Unpack,
    Concat,
    Slice,
    Extract,

    // Data movement
    Buffer,
    Route,
    Broadcast,

    // Pipeline (FPGA)
    Pipe,
    Delay,

    // FPGA DSP
    DspMul,
    DspMac,

    // Quantization
    Quant,
    Dequant,
    DequantW,

    // Softmax / activation
    Sub,     // subtract: (a, b) -> a - b
    Div,     // divide: (a, b) -> a / b
    Exp,     // exponential: (x) -> exp(x)
    Softmax, // composite softmax: (vec) -> vec

    // Identity/literals
    Const(i64),
    Var(usize), // name hash
    Zero,
    One,
    StrLit,

    // Accumulator
    AccInit,
    AccStep,
    AccRead,
    AccReset,
}

impl fmt::Display for AtomOp {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Const(v) => write!(f, "CONST({v})"),
            Self::Var(h) => write!(f, "VAR({h})"),
            _ => write!(f, "{:?}", self),
        }
    }
}

impl AtomOp {
    pub fn arity(&self) -> usize {
        match self {
            Self::Mul | Self::Add | Self::DspMul => 2,
            Self::Mac | Self::Madd | Self::DspMac => 3,
            Self::Shl | Self::Shr => 2,
            Self::Sat => 3,
            Self::Round => 2,
            Self::ReduceAdd | Self::ReduceMax | Self::ReduceMin => 2,
            Self::Scan => 2,
            Self::Pack | Self::Unpack | Self::Concat => 2,
            Self::Slice | Self::Extract => 3,
            Self::Buffer => 2,
            Self::Route => 3,
            Self::Broadcast => 2,
            Self::Pipe => 1,
            Self::Delay => 2,
            Self::Quant | Self::Dequant | Self::DequantW => 3,
            Self::Sub => 2,
            Self::Div => 2,
            Self::Exp => 1,
            Self::Softmax => 1,
            Self::Const(_) | Self::Var(_) | Self::StrLit => 0,
            Self::Zero | Self::One => 0,
            Self::AccInit => 1,
            Self::AccStep => 2,
            Self::AccRead => 1,
            Self::AccReset => 1,
        }
    }

    pub fn is_associative(&self) -> bool {
        matches!(
            self,
            Self::Add | Self::Mul | Self::Madd | Self::ReduceAdd | Self::ReduceMax | Self::ReduceMin | Self::Scan
        )
    }

    pub fn is_commutative(&self) -> bool {
        matches!(self, Self::Add | Self::Mul)
    }
}

/// An e-node: operation + list of e-class IDs for children
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ENode {
    pub op: AtomOp,
    pub children: Box<[u32]>, // e-class IDs
}

impl ENode {
    pub fn new(op: AtomOp, children: Vec<u32>) -> Self {
        Self {
            op,
            children: children.into_boxed_slice(),
        }
    }

    /// Create ENode with no children
    pub fn leaf(op: AtomOp) -> Self {
        Self {
            op,
            children: Box::new([]),
        }
    }
}
