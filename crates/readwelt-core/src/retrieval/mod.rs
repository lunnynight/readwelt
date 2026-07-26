//! Reusable native retrieval primitives.
//!
//! The lexical index owns document statistics and postings so callers build it
//! once during `prepare` and only send queries during the six reading stages.

mod dense;
mod fusion;
mod lexical;
mod selection;
mod types;

pub use dense::cosine_scores;
pub use fusion::hybrid_rrf;
pub use lexical::LexicalIndex;
pub use selection::select_evidence;
pub use types::{
    Bm25Variant, EvidenceSelection, HybridConfig, RankedDocument, RetrievalError, ScoringConfig,
};
