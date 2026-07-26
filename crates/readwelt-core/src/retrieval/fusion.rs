use super::{HybridConfig, RankedDocument, RetrievalError, types::sort_ranking};

/// Fuse a lexical ranking and one contiguous dense score per document with RRF.
pub fn hybrid_rrf(
    document_count: usize,
    lexical_ranking: &[RankedDocument],
    dense_scores: &[f32],
    config: HybridConfig,
    top_k: usize,
) -> Result<Vec<RankedDocument>, RetrievalError> {
    let config = config.validate()?;
    if dense_scores.len() != document_count {
        return Err(RetrievalError::DenseScoreCount {
            expected: document_count,
            actual: dense_scores.len(),
        });
    }
    for (document_ordinal, score) in dense_scores.iter().enumerate() {
        if !score.is_finite() {
            return Err(RetrievalError::NonFiniteDenseScore { document_ordinal });
        }
    }

    let mut seen = vec![false; document_count];
    let mut lexical = lexical_ranking.to_vec();
    for item in &lexical {
        if item.document_ordinal >= document_count {
            return Err(RetrievalError::LexicalDocumentOutOfRange {
                document_ordinal: item.document_ordinal,
            });
        }
        if std::mem::replace(&mut seen[item.document_ordinal], true) {
            return Err(RetrievalError::DuplicateLexicalDocument {
                document_ordinal: item.document_ordinal,
            });
        }
        if !item.score.is_finite() {
            return Err(RetrievalError::NonFiniteLexicalScore {
                document_ordinal: item.document_ordinal,
            });
        }
    }
    sort_ranking(&mut lexical);

    let mut dense: Vec<(usize, f32)> = dense_scores.iter().copied().enumerate().collect();
    dense.sort_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| left.0.cmp(&right.0))
    });

    let mut fused_scores = vec![0.0; document_count];
    for (rank, item) in lexical.iter().enumerate() {
        fused_scores[item.document_ordinal] +=
            config.lexical_weight / (config.rrf_k + rank as f64 + 1.0);
    }
    for (rank, (document_ordinal, _)) in dense.iter().enumerate() {
        fused_scores[*document_ordinal] += config.dense_weight / (config.rrf_k + rank as f64 + 1.0);
    }

    let mut ranking: Vec<RankedDocument> = fused_scores
        .into_iter()
        .enumerate()
        .map(|(document_ordinal, score)| RankedDocument {
            document_ordinal,
            score,
        })
        .collect();
    sort_ranking(&mut ranking);
    ranking.truncate(top_k.min(document_count));
    Ok(ranking)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn combines_channels_and_resolves_ties_stably() {
        let lexical = vec![
            RankedDocument {
                document_ordinal: 0,
                score: 2.0,
            },
            RankedDocument {
                document_ordinal: 1,
                score: 1.0,
            },
        ];
        let ranking = hybrid_rrf(
            3,
            &lexical,
            &[0.1, 0.8, 0.9],
            HybridConfig {
                rrf_k: 1.0,
                ..HybridConfig::default()
            },
            3,
        )
        .unwrap();
        assert_eq!(
            ranking
                .iter()
                .map(|item| item.document_ordinal)
                .collect::<Vec<_>>(),
            vec![0, 1, 2]
        );
    }

    #[test]
    fn rejects_shape_duplicates_and_inactive_channels() {
        assert_eq!(
            hybrid_rrf(2, &[], &[0.0], HybridConfig::default(), 2),
            Err(RetrievalError::DenseScoreCount {
                expected: 2,
                actual: 1
            })
        );
        let duplicate = [
            RankedDocument {
                document_ordinal: 0,
                score: 2.0,
            },
            RankedDocument {
                document_ordinal: 0,
                score: 1.0,
            },
        ];
        assert_eq!(
            hybrid_rrf(2, &duplicate, &[0.0, 1.0], HybridConfig::default(), 2),
            Err(RetrievalError::DuplicateLexicalDocument {
                document_ordinal: 0
            })
        );
        assert_eq!(
            hybrid_rrf(
                1,
                &[],
                &[0.0],
                HybridConfig {
                    lexical_weight: 0.0,
                    dense_weight: 0.0,
                    ..HybridConfig::default()
                },
                1
            ),
            Err(RetrievalError::NoActiveHybridChannel)
        );
    }
}
