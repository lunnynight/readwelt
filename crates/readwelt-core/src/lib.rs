//! Deterministic, CPU-only primitives for Readwelt.
//!
//! The public seam is intentionally small: prepare text for downstream
//! processing, and store immutable bytes by their content digest.

mod object_store;
mod semantic;
mod text;

pub use object_store::{ObjectStoreError, StoredObject, store_object};
pub use semantic::{SegmentAnalysis, analyze_segments, bm25_rank, coverage_intervals, tokenize};
pub use text::{Paragraph, PreparedText, prepare_text};
