use std::fmt;

/// Overflow behavior for arithmetic operations
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Default)]
pub enum OverflowMode {
    /// Modular/wrapping (e.g., unsigned 8-bit: 255 + 1 = 0)
    #[default]
    Wrap,
    /// Saturating (e.g., 255 + 1 = 255)
    Sat,
    /// Widened — no overflow possible (result width = max input width + 1)
    Wide,
}

/// Data type for arithmetic nodes
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct DataType {
    pub width: u32,
    pub signed: bool,
    pub overflow: OverflowMode,
}

impl DataType {
    pub const U8: DataType = DataType { width: 8, signed: false, overflow: OverflowMode::Wrap };
    pub const U16: DataType = DataType { width: 16, signed: false, overflow: OverflowMode::Wrap };
    pub const U32: DataType = DataType { width: 32, signed: false, overflow: OverflowMode::Wrap };
    pub const S16: DataType = DataType { width: 16, signed: true, overflow: OverflowMode::Wrap };
    pub const S32: DataType = DataType { width: 32, signed: true, overflow: OverflowMode::Wrap };
}

impl Default for DataType {
    fn default() -> Self { DataType::U16 }
}

impl DataType {
    /// Check if two types are compatible for binary arithmetic (same width + signedness)
    pub fn compatible(&self, other: &DataType) -> bool {
        self.width == other.width && self.signed == other.signed
    }

    /// Output type for binary arithmetic: wider ops produce wider result
    pub fn result_type(&self, other: &DataType, op_overflow: OverflowMode) -> DataType {
        let out_width = match op_overflow {
            OverflowMode::Wide => self.width.max(other.width) + 1,
            _ => self.width.max(other.width),
        };
        DataType { width: out_width, signed: self.signed || other.signed, overflow: op_overflow }
    }

    /// LUT cost for an adder of this width (rough: ~1 LUT per 4 bits per operator)
    pub fn adder_lut_cost(&self) -> f64 {
        (self.width as f64 / 4.0).ceil() * 0.5
    }

    /// DSP cost: fits in a single DSP48E1 slice? (25×18 multiplier)
    pub fn fits_dsp_mul(&self) -> bool {
        self.width <= 25
    }
}

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
    DspPreAdd,  // DSP48 pre-adder: (a ± b) × c in 1 slice

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

    // Streaming / FIFO (for pipeline kernels)
    StreamRead,   // read from input stream
    StreamWrite,  // write to output stream
    StreamFifo,   // FIFO buffer with depth
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
            Self::Mac | Self::Madd | Self::DspMac | Self::DspPreAdd => 3,
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
            Self::StreamRead => 0,
            Self::StreamWrite => 1,
            Self::StreamFifo => 1,
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

    /// Whether this op produces an arithmetic result (has a meaningful output type)
    pub fn is_arithmetic(&self) -> bool {
        matches!(self,
            Self::Add | Self::Sub | Self::Mul | Self::Mac | Self::Madd |
            Self::DspMul | Self::DspMac | Self::DspPreAdd | Self::Shl | Self::Shr |
            Self::ReduceAdd | Self::ReduceMax | Self::ReduceMin |
            Self::Sat | Self::Round | Self::Div | Self::Exp |
            Self::Quant | Self::Dequant | Self::DequantW
        )
    }

    /// Returns true if two ops can be reassociated (same op, compatible types)
    pub fn can_reassociate(&self, other: &AtomOp, t1: &DataType, t2: &DataType) -> bool {
        self == other && self.is_associative() && t1.compatible(t2)
    }
}

/// An e-node: operation + list of e-class IDs for children + data type
#[derive(Debug, Clone, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct ENode {
    pub op: AtomOp,
    pub children: Box<[u32]>,  // e-class IDs
    pub dtype: DataType,       // output data type
}

impl ENode {
    pub fn new(op: AtomOp, children: Vec<u32>, dtype: DataType) -> Self {
        Self {
            op,
            children: children.into_boxed_slice(),
            dtype,
        }
    }

    /// Create ENode with no children and default type
    pub fn leaf(op: AtomOp) -> Self {
        Self {
            op,
            children: Box::new([]),
            dtype: DataType::default(),
        }
    }

    /// Create leaf with specific data type
    pub fn leaf_typed(op: AtomOp, dtype: DataType) -> Self {
        Self { op, children: Box::new([]), dtype }
    }

    /// Unify types of children — returns the common result type for this op
    /// Returns None if children have incompatible types
    pub fn infer_dtype(op: AtomOp, child_dtypes: &[DataType]) -> Option<DataType> {
        if child_dtypes.is_empty() {
            return Some(DataType::default());
        }
        // Find the widest child type
        let mut base = child_dtypes[0];
        for ct in &child_dtypes[1..] {
            if !base.compatible(ct) { return None; }
            if ct.width > base.width { base.width = ct.width; }
        }
        // Result type depends on op and overflow
        let ov = if op == AtomOp::Sat { OverflowMode::Sat } else { OverflowMode::Wrap };
        Some(if child_dtypes.len() >= 2 {
            base.result_type(&child_dtypes[1], ov)
        } else {
            base
        })
    }
}