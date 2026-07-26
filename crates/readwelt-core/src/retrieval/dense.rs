use rayon::prelude::*;

use super::RetrievalError;

const PARALLEL_DOCUMENT_THRESHOLD: usize = 256;

/// Compute cosine scores from a query and row-major contiguous document vectors.
pub fn cosine_scores(
    query: &[f32],
    document_vectors: &[f32],
    dimensions: usize,
) -> Result<Vec<f32>, RetrievalError> {
    if dimensions == 0 {
        return Err(RetrievalError::ZeroDimensions);
    }
    if query.len() != dimensions {
        return Err(RetrievalError::QueryDimension {
            expected: dimensions,
            actual: query.len(),
        });
    }
    if document_vectors.len() % dimensions != 0 {
        return Err(RetrievalError::DocumentVectorShape {
            dimensions,
            actual: document_vectors.len(),
        });
    }
    if query
        .iter()
        .chain(document_vectors)
        .any(|value| !value.is_finite())
    {
        return Err(RetrievalError::NonFiniteVector);
    }

    let document_count = document_vectors.len() / dimensions;
    let score = |document: &[f32]| cosine(query, document);
    if document_count >= PARALLEL_DOCUMENT_THRESHOLD {
        Ok(document_vectors
            .par_chunks_exact(dimensions)
            .map(score)
            .collect())
    } else {
        Ok(document_vectors
            .chunks_exact(dimensions)
            .map(score)
            .collect())
    }
}

fn cosine(left: &[f32], right: &[f32]) -> f32 {
    let (dot, left_norm, right_norm) =
        left.iter()
            .zip(right)
            .fold((0.0_f64, 0.0_f64, 0.0_f64), |accumulator, values| {
                let left = f64::from(*values.0);
                let right = f64::from(*values.1);
                (
                    accumulator.0 + left * right,
                    accumulator.1 + left * left,
                    accumulator.2 + right * right,
                )
            });
    if left_norm == 0.0 || right_norm == 0.0 {
        0.0
    } else {
        (dot / (left_norm.sqrt() * right_norm.sqrt())) as f32
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn contiguous_scores_keep_document_order_and_validate_shape() {
        let scores = cosine_scores(&[1.0, 0.0], &[1.0, 0.0, 0.0, 1.0, -1.0, 0.0], 2).unwrap();
        assert_eq!(scores, vec![1.0, 0.0, -1.0]);
        assert_eq!(
            cosine_scores(&[1.0], &[1.0, 2.0], 0),
            Err(RetrievalError::ZeroDimensions)
        );
    }
}
