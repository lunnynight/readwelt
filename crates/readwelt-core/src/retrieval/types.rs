use thiserror::Error;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Bm25Variant {
    Bm25,
    Bm25Plus,
    Bm25L,
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ScoringConfig {
    pub variant: Bm25Variant,
    pub k1: f64,
    pub b: f64,
    pub delta: f64,
}

impl Default for ScoringConfig {
    fn default() -> Self {
        Self {
            variant: Bm25Variant::Bm25,
            k1: 1.5,
            b: 0.75,
            delta: 1.0,
        }
    }
}

impl ScoringConfig {
    pub(crate) fn validate(self) -> Result<Self, RetrievalError> {
        if !self.k1.is_finite() || self.k1 <= 0.0 {
            return Err(RetrievalError::InvalidK1(self.k1));
        }
        if !self.b.is_finite() || !(0.0..=1.0).contains(&self.b) {
            return Err(RetrievalError::InvalidB(self.b));
        }
        if !self.delta.is_finite() || self.delta < 0.0 {
            return Err(RetrievalError::InvalidDelta(self.delta));
        }
        Ok(self)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct HybridConfig {
    pub lexical_weight: f64,
    pub dense_weight: f64,
    pub rrf_k: f64,
}

impl Default for HybridConfig {
    fn default() -> Self {
        Self {
            lexical_weight: 1.0,
            dense_weight: 1.0,
            rrf_k: 60.0,
        }
    }
}

impl HybridConfig {
    pub(crate) fn validate(self) -> Result<Self, RetrievalError> {
        if !self.lexical_weight.is_finite() || self.lexical_weight < 0.0 {
            return Err(RetrievalError::InvalidWeight {
                channel: "lexical",
                value: self.lexical_weight,
            });
        }
        if !self.dense_weight.is_finite() || self.dense_weight < 0.0 {
            return Err(RetrievalError::InvalidWeight {
                channel: "dense",
                value: self.dense_weight,
            });
        }
        if self.lexical_weight == 0.0 && self.dense_weight == 0.0 {
            return Err(RetrievalError::NoActiveHybridChannel);
        }
        if !self.rrf_k.is_finite() || self.rrf_k <= 0.0 {
            return Err(RetrievalError::InvalidRrfK(self.rrf_k));
        }
        Ok(self)
    }
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct RankedDocument {
    pub document_ordinal: usize,
    pub score: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EvidenceSelection {
    pub selected_ordinals: Vec<usize>,
    pub omitted_ordinals: Vec<usize>,
    pub consumed_tokens: usize,
}

#[derive(Debug, Error, PartialEq)]
pub enum RetrievalError {
    #[error("BM25 k1 must be finite and greater than zero, got {0}")]
    InvalidK1(f64),
    #[error("BM25 b must be finite and within [0, 1], got {0}")]
    InvalidB(f64),
    #[error("BM25 delta must be finite and non-negative, got {0}")]
    InvalidDelta(f64),
    #[error("{channel} fusion weight must be finite and non-negative, got {value}")]
    InvalidWeight { channel: &'static str, value: f64 },
    #[error("at least one hybrid retrieval channel must have a positive weight")]
    NoActiveHybridChannel,
    #[error("RRF k must be finite and greater than zero, got {0}")]
    InvalidRrfK(f64),
    #[error("dense score count {actual} does not match document count {expected}")]
    DenseScoreCount { expected: usize, actual: usize },
    #[error("dense score at document {document_ordinal} is not finite")]
    NonFiniteDenseScore { document_ordinal: usize },
    #[error("lexical ranking contains out-of-range document {document_ordinal}")]
    LexicalDocumentOutOfRange { document_ordinal: usize },
    #[error("lexical ranking contains document {document_ordinal} more than once")]
    DuplicateLexicalDocument { document_ordinal: usize },
    #[error("lexical score at document {document_ordinal} is not finite")]
    NonFiniteLexicalScore { document_ordinal: usize },
    #[error("vector dimensions must be greater than zero")]
    ZeroDimensions,
    #[error("query vector has {actual} values, expected {expected}")]
    QueryDimension { expected: usize, actual: usize },
    #[error("document vector buffer has {actual} values, not a multiple of {dimensions}")]
    DocumentVectorShape { dimensions: usize, actual: usize },
    #[error("vector input contains a non-finite value")]
    NonFiniteVector,
    #[error("evidence field {field} has {actual} values, expected {expected} to match scores")]
    EvidenceInputLength {
        field: &'static str,
        expected: usize,
        actual: usize,
    },
    #[error("evidence score at document {document_ordinal} is not finite")]
    NonFiniteEvidenceScore { document_ordinal: usize },
}

pub(crate) fn sort_ranking(ranking: &mut [RankedDocument]) {
    ranking.sort_by(|left, right| {
        right
            .score
            .total_cmp(&left.score)
            .then_with(|| left.document_ordinal.cmp(&right.document_ordinal))
    });
}
