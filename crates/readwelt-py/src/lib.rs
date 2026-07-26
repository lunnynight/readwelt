use std::path::PathBuf;

use pyo3::{
    exceptions::{PyOSError, PyValueError},
    prelude::*,
};
use readwelt_core::{
    Bm25Variant, HybridConfig, LexicalIndex, Paragraph, PreparedText, RankedDocument,
    ScoringConfig, analyze_segments, bm25_rank, cosine_scores, coverage_intervals, hybrid_rrf,
    prepare_text, select_evidence, store_object,
};

type PySegmentAnalysis = (
    Vec<String>,
    usize,
    usize,
    usize,
    usize,
    String,
    Option<usize>,
    Vec<usize>,
);
type PyDenseRanking = (Vec<f32>, Vec<(usize, f32)>);
type PyEvidenceSelection = (Vec<usize>, Vec<usize>, usize);

#[pyclass(frozen, name = "ParagraphAnchor")]
struct PyParagraphAnchor {
    #[pyo3(get)]
    anchor_id: String,
    #[pyo3(get)]
    ordinal: usize,
    #[pyo3(get)]
    start_byte: usize,
    #[pyo3(get)]
    end_byte: usize,
    #[pyo3(get)]
    start_char: usize,
    #[pyo3(get)]
    end_char: usize,
    #[pyo3(get)]
    text: String,
}

impl From<Paragraph> for PyParagraphAnchor {
    fn from(value: Paragraph) -> Self {
        Self {
            anchor_id: value.anchor_id,
            ordinal: value.ordinal,
            start_byte: value.start_byte,
            end_byte: value.end_byte,
            start_char: value.start_char,
            end_char: value.end_char,
            text: value.text,
        }
    }
}

#[pyclass(frozen, name = "PreparedText")]
struct PyPreparedText {
    #[pyo3(get)]
    text: String,
    #[pyo3(get)]
    digest: String,
    #[pyo3(get)]
    paragraphs: Vec<Py<PyParagraphAnchor>>,
}

#[pyclass(frozen, name = "StoredObject")]
struct PyStoredObject {
    #[pyo3(get)]
    digest: String,
    #[pyo3(get)]
    relative_path: String,
    #[pyo3(get)]
    size: u64,
    #[pyo3(get)]
    created: bool,
}

#[pyclass(frozen, name = "RetrievalIndex")]
struct PyRetrievalIndex {
    index: LexicalIndex,
}

#[pyclass(frozen, name = "DenseIndex")]
struct PyDenseIndex {
    vectors: Vec<f32>,
    dimensions: usize,
    document_count: usize,
}

fn retrieval_value_error(error: impl std::fmt::Display) -> PyErr {
    PyValueError::new_err(error.to_string())
}

fn scoring_variant(value: &str) -> PyResult<Bm25Variant> {
    match value {
        "bm25" => Ok(Bm25Variant::Bm25),
        "bm25_plus" => Ok(Bm25Variant::Bm25Plus),
        "bm25_l" => Ok(Bm25Variant::Bm25L),
        _ => Err(PyValueError::new_err(format!(
            "unsupported lexical scorer: {value}"
        ))),
    }
}

#[pymethods]
impl PyRetrievalIndex {
    #[new]
    #[pyo3(signature = (documents, scorer="bm25_plus", k1=1.5, b=0.75, delta=1.0))]
    fn new(
        documents: Vec<Vec<String>>,
        scorer: &str,
        k1: f64,
        b: f64,
        delta: f64,
    ) -> PyResult<Self> {
        let config = ScoringConfig {
            variant: scoring_variant(scorer)?,
            k1,
            b,
            delta,
        };
        let index = LexicalIndex::new(&documents, config).map_err(retrieval_value_error)?;
        Ok(Self { index })
    }

    #[getter]
    fn document_count(&self) -> usize {
        self.index.document_count()
    }

    #[getter]
    fn vocabulary_size(&self) -> usize {
        self.index.vocabulary_size()
    }

    #[pyo3(signature = (query, top_k=None))]
    fn rank(
        &self,
        py: Python<'_>,
        query: Vec<String>,
        top_k: Option<usize>,
    ) -> PyResult<Vec<(usize, f64)>> {
        let limit = top_k.unwrap_or_else(|| self.index.document_count());
        if limit == 0 {
            return Err(PyValueError::new_err("top_k must be greater than zero"));
        }
        py.allow_threads(|| self.index.rank(&query, limit))
            .map(|ranking| {
                ranking
                    .into_iter()
                    .map(|item| (item.document_ordinal, item.score))
                    .collect()
            })
            .map_err(retrieval_value_error)
    }
}

#[pymethods]
impl PyDenseIndex {
    #[new]
    fn new(documents: Vec<Vec<f32>>, dimensions: usize) -> PyResult<Self> {
        if dimensions == 0 {
            return Err(PyValueError::new_err(
                "dense index dimensions must be greater than zero",
            ));
        }
        if documents
            .iter()
            .any(|document| document.len() != dimensions)
        {
            return Err(PyValueError::new_err(
                "dense document vector has an unexpected dimension",
            ));
        }
        let document_count = documents.len();
        let vectors = documents.into_iter().flatten().collect();
        Ok(Self {
            vectors,
            dimensions,
            document_count,
        })
    }

    #[getter]
    fn document_count(&self) -> usize {
        self.document_count
    }

    fn rank(&self, py: Python<'_>, queries: Vec<Vec<f32>>) -> PyResult<PyDenseRanking> {
        if queries.is_empty() {
            return Err(PyValueError::new_err(
                "dense index requires at least one query vector",
            ));
        }
        let scores = py
            .allow_threads(|| {
                let mut maximum = vec![f32::NEG_INFINITY; self.document_count];
                for query in &queries {
                    let current = cosine_scores(query, &self.vectors, self.dimensions)?;
                    for (target, score) in maximum.iter_mut().zip(current) {
                        *target = target.max(score);
                    }
                }
                Ok::<_, readwelt_core::RetrievalError>(maximum)
            })
            .map_err(retrieval_value_error)?;
        let mut ranking: Vec<(usize, f32)> = scores.iter().copied().enumerate().collect();
        ranking.sort_by(|left, right| {
            right
                .1
                .total_cmp(&left.1)
                .then_with(|| left.0.cmp(&right.0))
        });
        Ok((scores, ranking))
    }
}

#[pyfunction]
fn prepare(py: Python<'_>, text: &str) -> PyResult<PyPreparedText> {
    let PreparedText {
        text,
        digest,
        paragraphs,
    } = prepare_text(text);
    let paragraphs = paragraphs
        .into_iter()
        .map(|paragraph| Py::new(py, PyParagraphAnchor::from(paragraph)))
        .collect::<PyResult<Vec<_>>>()?;

    Ok(PyPreparedText {
        text,
        digest,
        paragraphs,
    })
}

#[pyfunction]
fn put_object(object_root: PathBuf, data: &[u8]) -> PyResult<PyStoredObject> {
    let stored =
        store_object(object_root, data).map_err(|error| PyOSError::new_err(error.to_string()))?;

    Ok(PyStoredObject {
        digest: stored.digest,
        relative_path: stored.relative_path.to_string_lossy().replace('\\', "/"),
        size: stored.size,
        created: stored.created,
    })
}

#[pyfunction]
fn semantic_analyze(
    py: Python<'_>,
    texts: Vec<String>,
    near_duplicate_threshold: f64,
) -> PyResult<Vec<PySegmentAnalysis>> {
    if !(0.0..=1.0).contains(&near_duplicate_threshold) {
        return Err(PyValueError::new_err(
            "near_duplicate_threshold must be between zero and one",
        ));
    }
    let results = py.allow_threads(|| analyze_segments(&texts, near_duplicate_threshold));
    Ok(results
        .into_iter()
        .map(|item| {
            (
                item.tokens,
                item.character_count,
                item.non_whitespace_character_count,
                item.token_count,
                item.sentence_boundary_count,
                item.exact_digest,
                item.exact_duplicate_ordinal,
                item.near_duplicate_ordinals,
            )
        })
        .collect())
}

#[pyfunction(name = "bm25_rank")]
#[pyo3(signature = (documents, query, k1=1.5, b=0.75))]
fn py_bm25_rank(
    py: Python<'_>,
    documents: Vec<Vec<String>>,
    query: Vec<String>,
    k1: f64,
    b: f64,
) -> Vec<(usize, f64)> {
    py.allow_threads(|| bm25_rank(&documents, &query, k1, b))
}

#[pyfunction(name = "cosine_scores")]
fn py_cosine_scores(
    py: Python<'_>,
    query: Vec<f32>,
    document_vectors: Vec<f32>,
    dimensions: usize,
) -> PyResult<Vec<f32>> {
    py.allow_threads(|| cosine_scores(&query, &document_vectors, dimensions))
        .map_err(retrieval_value_error)
}

#[pyfunction(name = "hybrid_rrf")]
#[pyo3(signature = (
    document_count,
    lexical_ranking,
    dense_scores,
    top_k,
    fusion=(1.0, 1.0, 60.0)
))]
fn py_hybrid_rrf(
    py: Python<'_>,
    document_count: usize,
    lexical_ranking: Vec<(usize, f64)>,
    dense_scores: Vec<f32>,
    top_k: usize,
    fusion: (f64, f64, f64),
) -> PyResult<Vec<(usize, f64)>> {
    if top_k == 0 {
        return Err(PyValueError::new_err("top_k must be greater than zero"));
    }
    let lexical: Vec<RankedDocument> = lexical_ranking
        .into_iter()
        .map(|(document_ordinal, score)| RankedDocument {
            document_ordinal,
            score,
        })
        .collect();
    let config = HybridConfig {
        lexical_weight: fusion.0,
        dense_weight: fusion.1,
        rrf_k: fusion.2,
    };
    py.allow_threads(|| hybrid_rrf(document_count, &lexical, &dense_scores, config, top_k))
        .map(|ranking| {
            ranking
                .into_iter()
                .map(|item| (item.document_ordinal, item.score))
                .collect()
        })
        .map_err(retrieval_value_error)
}

#[pyfunction(name = "select_evidence")]
fn py_select_evidence(
    py: Python<'_>,
    scores: Vec<f64>,
    section_ordinals: Vec<usize>,
    priority_flags: Vec<bool>,
    token_costs: Vec<usize>,
    token_budget: usize,
) -> PyResult<PyEvidenceSelection> {
    py.allow_threads(|| {
        select_evidence(
            &scores,
            &section_ordinals,
            &priority_flags,
            &token_costs,
            token_budget,
        )
    })
    .map(|selection| {
        (
            selection.selected_ordinals,
            selection.omitted_ordinals,
            selection.consumed_tokens,
        )
    })
    .map_err(retrieval_value_error)
}

#[pyfunction(name = "coverage_intervals")]
fn py_coverage_intervals(
    py: Python<'_>,
    text: String,
    ranges: Vec<(usize, usize)>,
) -> PyResult<(Vec<(usize, usize)>, usize)> {
    let character_count = text.chars().count();
    if ranges
        .iter()
        .any(|(start, end)| start > end || *end > character_count)
    {
        return Err(PyValueError::new_err("coverage range is outside text"));
    }
    Ok(py.allow_threads(|| coverage_intervals(&text, &ranges)))
}

#[pymodule]
fn _core(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<PyParagraphAnchor>()?;
    module.add_class::<PyPreparedText>()?;
    module.add_class::<PyStoredObject>()?;
    module.add_class::<PyRetrievalIndex>()?;
    module.add_class::<PyDenseIndex>()?;
    module.add_function(wrap_pyfunction!(prepare, module)?)?;
    module.add_function(wrap_pyfunction!(put_object, module)?)?;
    module.add_function(wrap_pyfunction!(semantic_analyze, module)?)?;
    module.add_function(wrap_pyfunction!(py_bm25_rank, module)?)?;
    module.add_function(wrap_pyfunction!(py_cosine_scores, module)?)?;
    module.add_function(wrap_pyfunction!(py_hybrid_rrf, module)?)?;
    module.add_function(wrap_pyfunction!(py_select_evidence, module)?)?;
    module.add_function(wrap_pyfunction!(py_coverage_intervals, module)?)?;
    Ok(())
}
