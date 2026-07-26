//! Deterministic, CPU-only primitives for Readwelt.
//!
//! The public seam is intentionally small: prepare text for downstream
//! processing, and store immutable bytes by their content digest.

mod object_store;
pub mod retrieval;
mod semantic;
mod text;

pub use object_store::{ObjectStoreError, StoredObject, store_object};
pub use retrieval::{
    Bm25Variant, EvidenceSelection, HybridConfig, LexicalIndex, RankedDocument, RetrievalError,
    ScoringConfig, cosine_scores, hybrid_rrf, select_evidence,
};
pub use semantic::{SegmentAnalysis, analyze_segments, bm25_rank, coverage_intervals, tokenize};
pub use text::{Paragraph, PreparedText, prepare_text};
