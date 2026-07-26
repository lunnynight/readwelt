use std::collections::{BTreeMap, BTreeSet};

use super::types::{Bm25Variant, RankedDocument, RetrievalError, ScoringConfig, sort_ranking};

#[derive(Debug, Clone)]
struct Posting {
    document_ordinal: usize,
    term_frequency: usize,
}

#[derive(Debug, Clone)]
struct TermPostings {
    inverse_document_frequency: f64,
    postings: Vec<Posting>,
}

/// An immutable lexical index reusable across all retrieval plans for a source.
#[derive(Debug, Clone)]
pub struct LexicalIndex {
    document_lengths: Vec<usize>,
    average_document_length: f64,
    terms: BTreeMap<String, TermPostings>,
    config: ScoringConfig,
}

impl LexicalIndex {
    pub fn new(documents: &[Vec<String>], config: ScoringConfig) -> Result<Self, RetrievalError> {
        let config = config.validate()?;
        let document_lengths: Vec<usize> = documents.iter().map(Vec::len).collect();
        let average_document_length = if documents.is_empty() {
            0.0
        } else {
            document_lengths.iter().sum::<usize>() as f64 / documents.len() as f64
        };
        let mut raw_postings: BTreeMap<String, Vec<Posting>> = BTreeMap::new();

        for (document_ordinal, document) in documents.iter().enumerate() {
            let mut frequencies: BTreeMap<&str, usize> = BTreeMap::new();
            for token in document {
                *frequencies.entry(token).or_default() += 1;
            }
            for (token, term_frequency) in frequencies {
                raw_postings
                    .entry(token.to_owned())
                    .or_default()
                    .push(Posting {
                        document_ordinal,
                        term_frequency,
                    });
            }
        }

        let document_count = documents.len() as f64;
        let terms = raw_postings
            .into_iter()
            .map(|(token, postings)| {
                let document_frequency = postings.len() as f64;
                let inverse_document_frequency = (1.0
                    + (document_count - document_frequency + 0.5) / (document_frequency + 0.5))
                    .ln();
                (
                    token,
                    TermPostings {
                        inverse_document_frequency,
                        postings,
                    },
                )
            })
            .collect();

        Ok(Self {
            document_lengths,
            average_document_length,
            terms,
            config,
        })
    }

    #[must_use]
    pub fn document_count(&self) -> usize {
        self.document_lengths.len()
    }

    #[must_use]
    pub fn vocabulary_size(&self) -> usize {
        self.terms.len()
    }

    /// Rank documents by descending score and then ascending source ordinal.
    pub fn rank(
        &self,
        query: &[String],
        top_k: usize,
    ) -> Result<Vec<RankedDocument>, RetrievalError> {
        let limit = top_k.min(self.document_count());
        if limit == 0 {
            return Ok(Vec::new());
        }

        let mut scores = vec![0.0; self.document_count()];
        let unique_query: BTreeSet<&str> = query.iter().map(String::as_str).collect();
        if self.average_document_length > 0.0 {
            for token in unique_query {
                let Some(term) = self.terms.get(token) else {
                    continue;
                };
                for posting in &term.postings {
                    let document_length = self.document_lengths[posting.document_ordinal] as f64;
                    scores[posting.document_ordinal] += term.inverse_document_frequency
                        * term_weight(
                            posting.term_frequency as f64,
                            document_length,
                            self.average_document_length,
                            self.config,
                        );
                }
            }
        }

        let mut ranking: Vec<RankedDocument> = scores
            .into_iter()
            .enumerate()
            .map(|(document_ordinal, score)| RankedDocument {
                document_ordinal,
                score,
            })
            .collect();
        sort_ranking(&mut ranking);
        ranking.truncate(limit);
        Ok(ranking)
    }
}

fn term_weight(
    term_frequency: f64,
    document_length: f64,
    average_document_length: f64,
    config: ScoringConfig,
) -> f64 {
    let length_normalization =
        1.0 - config.b + config.b * document_length / average_document_length;
    match config.variant {
        Bm25Variant::Bm25 => {
            term_frequency * (config.k1 + 1.0) / (term_frequency + config.k1 * length_normalization)
        }
        Bm25Variant::Bm25Plus => {
            term_frequency * (config.k1 + 1.0) / (term_frequency + config.k1 * length_normalization)
                + config.delta
        }
        Bm25Variant::Bm25L => {
            let normalized_frequency = term_frequency / length_normalization;
            term_frequency * (config.k1 + 1.0) * (normalized_frequency + config.delta)
                / (config.k1 + normalized_frequency + config.delta)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tokens(values: &[&str]) -> Vec<String> {
        values.iter().map(|value| (*value).to_owned()).collect()
    }

    #[test]
    fn exact_term_ranks_matching_document_first() {
        let index = LexicalIndex::new(
            &[
                tokens(&["market", "price"]),
                tokens(&["quantum", "chip", "quantum"]),
                tokens(&["music", "melody"]),
            ],
            ScoringConfig::default(),
        )
        .expect("valid index");
        let ranking = index.rank(&tokens(&["quantum"]), 3).expect("valid ranking");
        assert_eq!(ranking[0].document_ordinal, 1);
        assert!(ranking[0].score > ranking[1].score);
        assert_eq!(index.document_count(), 3);
        assert_eq!(index.vocabulary_size(), 6);
    }

    #[test]
    fn bm25_plus_preserves_a_lower_bound_for_a_long_matching_document() {
        let mut long = vec!["target".to_owned()];
        long.extend((0..999).map(|ordinal| format!("filler-{ordinal}")));
        let config = ScoringConfig {
            variant: Bm25Variant::Bm25Plus,
            delta: 1.0,
            ..ScoringConfig::default()
        };
        let index = LexicalIndex::new(&[tokens(&["target"]), long], config).expect("valid index");
        let ranking = index.rank(&tokens(&["target"]), 2).expect("valid ranking");
        let long_score = ranking
            .iter()
            .find(|item| item.document_ordinal == 1)
            .expect("long document is ranked")
            .score;
        let idf = (1.0_f64 + 0.5 / 2.5).ln();
        assert!(long_score >= idf * config.delta);
    }

    #[test]
    fn all_variants_produce_finite_positive_matches() {
        for variant in [Bm25Variant::Bm25, Bm25Variant::Bm25Plus, Bm25Variant::Bm25L] {
            let index = LexicalIndex::new(
                &[tokens(&["target"]), tokens(&["other"])],
                ScoringConfig {
                    variant,
                    ..ScoringConfig::default()
                },
            )
            .expect("valid index");
            let ranking = index.rank(&tokens(&["target"]), 2).expect("valid ranking");
            assert!(ranking[0].score.is_finite());
            assert!(ranking[0].score > 0.0);
        }
    }

    #[test]
    fn ties_are_stable_by_source_ordinal() {
        let tied = LexicalIndex::new(
            &[tokens(&["same"]), tokens(&["same"]), tokens(&["same"])],
            ScoringConfig::default(),
        )
        .unwrap()
        .rank(&tokens(&["same"]), 3)
        .unwrap();
        assert_eq!(
            tied.iter()
                .map(|item| item.document_ordinal)
                .collect::<Vec<_>>(),
            vec![0, 1, 2]
        );
    }

    #[test]
    fn invalid_bm25_parameters_are_rejected() {
        assert_eq!(
            LexicalIndex::new(
                &[tokens(&["term"])],
                ScoringConfig {
                    b: 1.5,
                    ..ScoringConfig::default()
                }
            )
            .unwrap_err(),
            RetrievalError::InvalidB(1.5)
        );
        assert_eq!(
            LexicalIndex::new(
                &[tokens(&["term"])],
                ScoringConfig {
                    k1: 0.0,
                    ..ScoringConfig::default()
                }
            )
            .unwrap_err(),
            RetrievalError::InvalidK1(0.0)
        );
        assert_eq!(
            LexicalIndex::new(
                &[tokens(&["term"])],
                ScoringConfig {
                    delta: -0.1,
                    ..ScoringConfig::default()
                }
            )
            .unwrap_err(),
            RetrievalError::InvalidDelta(-0.1)
        );
    }
}
