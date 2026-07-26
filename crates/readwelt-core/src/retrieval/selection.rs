use std::collections::{BTreeMap, VecDeque};

use super::{EvidenceSelection, RetrievalError};

/// Select evidence with priority anchors, section balancing, and a strict budget.
pub fn select_evidence(
    scores: &[f64],
    section_ordinals: &[usize],
    priority_flags: &[bool],
    token_costs: &[usize],
    token_budget: usize,
) -> Result<EvidenceSelection, RetrievalError> {
    validate_inputs(scores, section_ordinals, priority_flags, token_costs)?;

    let mut priority_ordinals: Vec<usize> = priority_flags
        .iter()
        .enumerate()
        .filter_map(|(ordinal, priority)| priority.then_some(ordinal))
        .collect();
    priority_ordinals.sort_by(|left, right| compare(*left, *right, scores));

    let mut section_candidates: BTreeMap<usize, Vec<usize>> = BTreeMap::new();
    for (ordinal, section_ordinal) in section_ordinals.iter().copied().enumerate() {
        if !priority_flags[ordinal] {
            section_candidates
                .entry(section_ordinal)
                .or_default()
                .push(ordinal);
        }
    }
    let mut queues: BTreeMap<usize, VecDeque<usize>> = section_candidates
        .into_iter()
        .map(|(section, mut candidates)| {
            candidates.sort_by(|left, right| compare(*left, *right, scores));
            (section, candidates.into())
        })
        .collect();

    let mut ordered = priority_ordinals;
    while queues.values().any(|queue| !queue.is_empty()) {
        let mut active: Vec<(usize, usize)> = queues
            .iter()
            .filter_map(|(section, queue)| queue.front().copied().map(|head| (*section, head)))
            .collect();
        active.sort_by(|left, right| {
            scores[right.1]
                .total_cmp(&scores[left.1])
                .then_with(|| left.0.cmp(&right.0))
        });
        for (section, _) in active {
            ordered.push(
                queues
                    .get_mut(&section)
                    .and_then(VecDeque::pop_front)
                    .expect("active section has a head"),
            );
        }
    }

    let mut selected_ordinals = Vec::new();
    let mut omitted_ordinals = Vec::new();
    let mut consumed_tokens = 0;
    for ordinal in ordered {
        let cost = token_costs[ordinal];
        if cost <= token_budget - consumed_tokens {
            selected_ordinals.push(ordinal);
            consumed_tokens += cost;
        } else {
            omitted_ordinals.push(ordinal);
        }
    }
    Ok(EvidenceSelection {
        selected_ordinals,
        omitted_ordinals,
        consumed_tokens,
    })
}

fn validate_inputs(
    scores: &[f64],
    section_ordinals: &[usize],
    priority_flags: &[bool],
    token_costs: &[usize],
) -> Result<(), RetrievalError> {
    for (field, actual) in [
        ("section_ordinals", section_ordinals.len()),
        ("priority_flags", priority_flags.len()),
        ("token_costs", token_costs.len()),
    ] {
        if actual != scores.len() {
            return Err(RetrievalError::EvidenceInputLength {
                field,
                expected: scores.len(),
                actual,
            });
        }
    }
    for (document_ordinal, score) in scores.iter().enumerate() {
        if !score.is_finite() {
            return Err(RetrievalError::NonFiniteEvidenceScore { document_ordinal });
        }
    }
    Ok(())
}

fn compare(left: usize, right: usize, scores: &[f64]) -> std::cmp::Ordering {
    scores[right]
        .total_cmp(&scores[left])
        .then_with(|| left.cmp(&right))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reproduces_priority_round_robin_and_strict_budget() {
        let selection = select_evidence(
            &[9.0, 8.0, 4.0, 6.0, 7.0],
            &[0, 1, 0, 1, 1],
            &[false, false, false, true, false],
            &[4, 5, 1, 3, 1],
            8,
        )
        .unwrap();
        assert_eq!(selection.selected_ordinals, vec![3, 0, 4]);
        assert_eq!(selection.omitted_ordinals, vec![1, 2]);
        assert_eq!(selection.consumed_tokens, 8);
    }

    #[test]
    fn uses_source_section_order_and_stable_priority_ties() {
        let selection = select_evidence(
            &[1.0, 1.0, 1.0, 1.0],
            &[5, 3, 5, 3],
            &[true, true, false, false],
            &[1, 1, 1, 1],
            4,
        )
        .unwrap();
        assert_eq!(selection.selected_ordinals, vec![0, 1, 3, 2]);
        assert!(selection.omitted_ordinals.is_empty());
    }

    #[test]
    fn rejects_misaligned_and_nonfinite_inputs() {
        assert_eq!(
            select_evidence(&[1.0], &[], &[false], &[1], 1),
            Err(RetrievalError::EvidenceInputLength {
                field: "section_ordinals",
                expected: 1,
                actual: 0,
            })
        );
        assert_eq!(
            select_evidence(&[f64::NAN], &[0], &[false], &[1], 1),
            Err(RetrievalError::NonFiniteEvidenceScore {
                document_ordinal: 0,
            })
        );
    }
}
