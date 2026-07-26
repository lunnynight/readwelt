//! Batched lexical primitives used by the semantic preprocessing layer.
//!
//! These functions deliberately operate on strings, ordinals, and intervals.
//! Stable domain identifiers and policy remain in Python.

use std::collections::{BTreeMap, BTreeSet};

use blake2::{
    Blake2bVar,
    digest::{Update, VariableOutput},
};
use sha2::{Digest, Sha256};

const MINHASH_PERMUTATIONS: usize = 32;
const MINHASH_SEED: &[u8] = b"readwelt-minhash-v1\0";

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SegmentAnalysis {
    pub tokens: Vec<String>,
    pub character_count: usize,
    pub non_whitespace_character_count: usize,
    pub token_count: usize,
    pub sentence_boundary_count: usize,
    pub exact_digest: String,
    pub exact_duplicate_ordinal: Option<usize>,
    pub near_duplicate_ordinals: Vec<usize>,
}

/// Analyze all anchor texts in one native call and compare MinHash signatures
/// while the data is already resident in Rust.
#[must_use]
pub fn analyze_segments(texts: &[String], near_duplicate_threshold: f64) -> Vec<SegmentAnalysis> {
    assert!((0.0..=1.0).contains(&near_duplicate_threshold));

    let tokens: Vec<Vec<String>> = texts.iter().map(|text| tokenize(text)).collect();
    let digests: Vec<String> = texts
        .iter()
        .map(|text| sha256_hex(text.as_bytes()))
        .collect();
    let signatures: Vec<Vec<u64>> = tokens.iter().map(|items| minhash(items)).collect();
    let mut first_by_digest: BTreeMap<&str, usize> = BTreeMap::new();

    texts
        .iter()
        .enumerate()
        .map(|(ordinal, text)| {
            let exact_duplicate_ordinal = first_by_digest.get(digests[ordinal].as_str()).copied();
            first_by_digest
                .entry(digests[ordinal].as_str())
                .or_insert(ordinal);
            let near_duplicate_ordinals = (0..ordinal)
                .filter(|prior| {
                    digests[ordinal] != digests[*prior]
                        && signature_similarity(&signatures[ordinal], &signatures[*prior])
                            >= near_duplicate_threshold
                })
                .collect();
            SegmentAnalysis {
                tokens: tokens[ordinal].clone(),
                character_count: text.chars().count(),
                non_whitespace_character_count: text
                    .chars()
                    .filter(|character| !character.is_whitespace())
                    .count(),
                token_count: estimate_tokens(text, &tokens[ordinal]),
                sentence_boundary_count: sentence_boundary_count(text),
                exact_digest: digests[ordinal].clone(),
                exact_duplicate_ordinal,
                near_duplicate_ordinals,
            }
        })
        .collect()
}

/// Tokenize English/Latin as lowercase words and Chinese as characters plus
/// adjacent bigrams. This mirrors `readwelt-zh-bigram-en-word-v1`.
#[must_use]
pub fn tokenize(text: &str) -> Vec<String> {
    let characters: Vec<char> = text.chars().collect();
    let mut units = Vec::new();
    let mut cursor = 0;
    while cursor < characters.len() {
        let character = characters[cursor];
        if is_cjk(character) {
            units.push(character.to_string());
            cursor += 1;
            continue;
        }
        if !is_latin_word_base(character) {
            cursor += 1;
            continue;
        }

        let mut token = String::new();
        push_casefolded(&mut token, character);
        cursor += 1;
        while cursor < characters.len() {
            let next = characters[cursor];
            if is_latin_word_base(next) {
                push_casefolded(&mut token, next);
                cursor += 1;
            } else if is_connector(next)
                && cursor + 1 < characters.len()
                && is_latin_word_base(characters[cursor + 1])
            {
                token.push(next);
                cursor += 1;
            } else {
                break;
            }
        }
        units.push(token);
    }

    let mut result = units.clone();
    result.extend(units.windows(2).filter_map(|pair| {
        if is_single_cjk(&pair[0]) && is_single_cjk(&pair[1]) {
            Some(format!("{}{}", pair[0], pair[1]))
        } else {
            None
        }
    }));
    result
}

/// Rank tokenized documents with the compatibility BM25 formula.
#[must_use]
pub fn bm25_rank(
    documents: &[Vec<String>],
    query: &[String],
    k1: f64,
    b: f64,
) -> Vec<(usize, f64)> {
    let average_length = if documents.is_empty() {
        0.0
    } else {
        documents.iter().map(Vec::len).sum::<usize>() as f64 / documents.len() as f64
    };
    let mut document_frequency: BTreeMap<&str, usize> = BTreeMap::new();
    for document in documents {
        for token in document.iter().map(String::as_str).collect::<BTreeSet<_>>() {
            *document_frequency.entry(token).or_default() += 1;
        }
    }
    let size = documents.len() as f64;
    let idf: BTreeMap<&str, f64> = document_frequency
        .into_iter()
        .map(|(token, frequency)| {
            let frequency = frequency as f64;
            (
                token,
                (1.0 + (size - frequency + 0.5) / (frequency + 0.5)).ln(),
            )
        })
        .collect();
    let unique_query: BTreeSet<&str> = query.iter().map(String::as_str).collect();
    let mut scores: Vec<(usize, f64)> = documents
        .iter()
        .enumerate()
        .map(|(ordinal, document)| {
            if unique_query.is_empty() || average_length == 0.0 {
                return (ordinal, 0.0);
            }
            let mut counts: BTreeMap<&str, usize> = BTreeMap::new();
            for token in document {
                *counts.entry(token).or_default() += 1;
            }
            let score = unique_query
                .iter()
                .filter_map(|token| {
                    let frequency = *counts.get(token)? as f64;
                    let denominator =
                        frequency + k1 * (1.0 - b + b * document.len() as f64 / average_length);
                    Some(
                        idf.get(token).copied().unwrap_or_default() * frequency * (k1 + 1.0)
                            / denominator,
                    )
                })
                .sum();
            (ordinal, score)
        })
        .collect();
    scores.sort_by(|left, right| {
        right
            .1
            .total_cmp(&left.1)
            .then_with(|| left.0.cmp(&right.0))
    });
    scores
}

/// Return uncovered non-whitespace character intervals and the union length of
/// all covered character intervals.
#[must_use]
pub fn coverage_intervals(text: &str, ranges: &[(usize, usize)]) -> (Vec<(usize, usize)>, usize) {
    let characters: Vec<char> = text.chars().collect();
    let mut covered = vec![false; characters.len()];
    for &(start, end) in ranges {
        assert!(start <= end && end <= characters.len());
        covered[start..end].fill(true);
    }
    let mut uncovered = Vec::new();
    let mut start = None;
    for (offset, character) in characters.iter().enumerate() {
        let missing = !covered[offset] && !character.is_whitespace();
        match (missing, start) {
            (true, None) => start = Some(offset),
            (false, Some(begin)) => {
                uncovered.push((begin, offset));
                start = None;
            }
            _ => {}
        }
    }
    if let Some(begin) = start {
        uncovered.push((begin, characters.len()));
    }
    (uncovered, covered.iter().filter(|value| **value).count())
}

fn minhash(tokens: &[String]) -> Vec<u64> {
    let shingles: BTreeSet<&str> = tokens.iter().map(String::as_str).collect();
    if shingles.is_empty() {
        return Vec::new();
    }
    (0..MINHASH_PERMUTATIONS)
        .map(|permutation| {
            shingles
                .iter()
                .map(|token| {
                    let mut hasher = Blake2bVar::new(8).expect("eight-byte Blake2b is valid");
                    hasher.update(MINHASH_SEED);
                    hasher.update(&(permutation as u16).to_be_bytes());
                    hasher.update(token.as_bytes());
                    let mut output = [0_u8; 8];
                    hasher
                        .finalize_variable(&mut output)
                        .expect("output length was configured");
                    u64::from_be_bytes(output)
                })
                .min()
                .expect("non-empty shingles")
        })
        .collect()
}

fn signature_similarity(left: &[u64], right: &[u64]) -> f64 {
    if left.is_empty() || right.is_empty() {
        return 0.0;
    }
    left.iter()
        .zip(right)
        .filter(|(left_value, right_value)| left_value == right_value)
        .count() as f64
        / left.len() as f64
}

fn estimate_tokens(text: &str, tokens: &[String]) -> usize {
    if text.is_empty() {
        return 0;
    }
    let latin_units = tokens
        .iter()
        .filter(|token| token.chars().count() > 1 && token.is_ascii())
        .count();
    let cjk_chars = text.chars().filter(|character| is_cjk(*character)).count();
    let other = text.chars().count() - cjk_chars;
    1.max(cjk_chars + latin_units + other.div_ceil(12))
}

fn sentence_boundary_count(text: &str) -> usize {
    let mut count = 0;
    let mut inside_boundary = false;
    for character in text.chars() {
        let boundary = matches!(character, '.' | '!' | '?' | '。' | '！' | '？');
        if boundary && !inside_boundary {
            count += 1;
        }
        inside_boundary = boundary;
    }
    count
}

fn sha256_hex(input: &[u8]) -> String {
    format!("{:x}", Sha256::digest(input))
}

fn is_cjk(character: char) -> bool {
    ('\u{3400}'..='\u{9fff}').contains(&character)
}

fn is_latin_word_base(character: char) -> bool {
    character.is_ascii_alphanumeric()
        || ('\u{00c0}'..='\u{00d6}').contains(&character)
        || ('\u{00d8}'..='\u{00f6}').contains(&character)
        || ('\u{00f8}'..='\u{00ff}').contains(&character)
}

fn is_connector(character: char) -> bool {
    matches!(character, '\'' | '’' | '_' | '-')
}

fn push_casefolded(output: &mut String, character: char) {
    if character == 'ß' {
        output.push_str("ss");
    } else {
        output.extend(character.to_lowercase());
    }
}

fn is_single_cjk(token: &str) -> bool {
    let mut characters = token.chars();
    matches!(
        (characters.next(), characters.next()),
        (Some(character), None) if is_cjk(character)
    )
}

#[cfg(test)]
mod tests {
    use super::{analyze_segments, bm25_rank, coverage_intervals, tokenize};

    #[test]
    fn tokenizer_preserves_v1_chinese_and_latin_behavior() {
        assert_eq!(
            tokenize("量子芯片 Café's A_B ß"),
            vec![
                "量", "子", "芯", "片", "café's", "a_b", "ss", "量子", "子芯", "芯片"
            ]
        );
    }

    #[test]
    fn batch_analysis_finds_exact_and_near_duplicates() {
        let values = vec![
            "知识图谱用于检索。".to_owned(),
            "知识图谱用于检索。".to_owned(),
            "知识图谱可以用于检索。".to_owned(),
        ];
        let analysis = analyze_segments(&values, 0.5);
        assert_eq!(analysis[1].exact_duplicate_ordinal, Some(0));
        assert_eq!(analysis[2].near_duplicate_ordinals, vec![0, 1]);
    }

    #[test]
    fn bm25_and_coverage_are_stable() {
        let documents = vec![
            tokenize("苹果香蕉水果"),
            tokenize("量子计算芯片"),
            tokenize("古典音乐旋律"),
        ];
        assert_eq!(
            bm25_rank(&documents, &tokenize("量子芯片"), 1.5, 0.75)[0].0,
            1
        );
        assert_eq!(
            coverage_intervals("已锚定。关键遗漏。", &[(0, 4)]),
            (vec![(4, 9)], 4)
        );
    }
}
