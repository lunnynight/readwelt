use std::path::PathBuf;

use pyo3::{
    exceptions::{PyOSError, PyValueError},
    prelude::*,
};
use readwelt_core::{
    Paragraph, PreparedText, analyze_segments, bm25_rank, coverage_intervals, prepare_text,
    store_object,
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
    module.add_function(wrap_pyfunction!(prepare, module)?)?;
    module.add_function(wrap_pyfunction!(put_object, module)?)?;
    module.add_function(wrap_pyfunction!(semantic_analyze, module)?)?;
    module.add_function(wrap_pyfunction!(py_bm25_rank, module)?)?;
    module.add_function(wrap_pyfunction!(py_coverage_intervals, module)?)?;
    Ok(())
}
