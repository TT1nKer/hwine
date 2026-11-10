use crate::ir::AtomOp;

#[derive(Debug, Clone, PartialEq)]
pub enum HwineError {
    InvalidClass(u32),
    DeletedClass(u32),
    CycleDetected(u32),
    UnsupportedRtlOp(AtomOp),
    PortConflict {
        name: String,
        declared_as: String,
        conflicting_as: String,
    },
    InvalidInput(&'static str),
    ExtractionFailed(String),
}

pub type HwineResult<T> = Result<T, HwineError>;

impl std::fmt::Display for HwineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::InvalidClass(cid) => write!(f, "invalid e-class: {}", cid),
            Self::DeletedClass(cid) => write!(f, "deleted e-class: {}", cid),
            Self::CycleDetected(cid) => write!(f, "cycle detected at e-class {}", cid),
            Self::UnsupportedRtlOp(op) => write!(f, "RTL generation unsupported for {:?}", op),
            Self::PortConflict {
                name,
                declared_as,
                conflicting_as,
            } => {
                write!(
                    f,
                    "port conflict: '{}' declared as {} but already {}",
                    name, declared_as, conflicting_as
                )
            }
            Self::InvalidInput(msg) => write!(f, "invalid input: {}", msg),
            Self::ExtractionFailed(msg) => write!(f, "extraction failed: {}", msg),
        }
    }
}

impl std::error::Error for HwineError {}
