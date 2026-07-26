use std::{
    hint::black_box,
    time::{Duration, Instant},
};

use readwelt_core::{Bm25Variant, LexicalIndex, ScoringConfig, cosine_scores, select_evidence};

fn main() {
    lexical_queries_reuse_one_index();
    contiguous_dense_scan();
    native_evidence_selection();
}

fn native_evidence_selection() {
    const DOCUMENTS: usize = 5_000;
    let scores: Vec<f64> = (0..DOCUMENTS)
        .map(|ordinal| ((ordinal * 37) % DOCUMENTS) as f64)
        .collect();
    let sections: Vec<usize> = (0..DOCUMENTS).map(|ordinal| ordinal / 50).collect();
    let priorities: Vec<bool> = (0..DOCUMENTS).map(|ordinal| ordinal < 10).collect();
    let costs: Vec<usize> = (0..DOCUMENTS).map(|ordinal| 20 + ordinal % 80).collect();
    let started = Instant::now();
    let mut iterations = 0_u64;
    while started.elapsed() < Duration::from_millis(750) {
        black_box(
            select_evidence(
                black_box(&scores),
                black_box(&sections),
                black_box(&priorities),
                black_box(&costs),
                50_000,
            )
            .expect("valid benchmark evidence"),
        );
        iterations += 1;
    }
    let elapsed = started.elapsed();
    println!(
        "retrieval_core evidence: {iterations} selections, {:.0} candidates/s",
        iterations as f64 * DOCUMENTS as f64 / elapsed.as_secs_f64()
    );
}

fn lexical_queries_reuse_one_index() {
    let documents: Vec<Vec<String>> = (0..5_000)
        .map(|ordinal| {
            [
                "文章".to_owned(),
                "结构".to_owned(),
                format!("章节-{}", ordinal % 100),
                format!("主题-{}", ordinal % 25),
            ]
            .into_iter()
            .collect()
        })
        .collect();
    let index = LexicalIndex::new(
        &documents,
        ScoringConfig {
            variant: Bm25Variant::Bm25Plus,
            ..ScoringConfig::default()
        },
    )
    .expect("valid benchmark index");
    let query = vec!["主题-7".to_owned(), "结构".to_owned()];
    let started = Instant::now();
    let mut iterations = 0_u64;
    while started.elapsed() < Duration::from_millis(750) {
        black_box(
            index
                .rank(black_box(&query), 50)
                .expect("valid benchmark query"),
        );
        iterations += 1;
    }
    let elapsed = started.elapsed();
    println!(
        "retrieval_core lexical: {iterations} queries, {:.0} queries/s",
        iterations as f64 / elapsed.as_secs_f64()
    );
}

fn contiguous_dense_scan() {
    const DOCUMENTS: usize = 5_000;
    const DIMENSIONS: usize = 384;
    let query = vec![0.5_f32; DIMENSIONS];
    let vectors: Vec<f32> = (0..DOCUMENTS * DIMENSIONS)
        .map(|offset| (offset % 17) as f32 / 17.0)
        .collect();
    let started = Instant::now();
    let mut iterations = 0_u64;
    while started.elapsed() < Duration::from_millis(750) {
        black_box(
            cosine_scores(black_box(&query), black_box(&vectors), DIMENSIONS)
                .expect("valid benchmark vectors"),
        );
        iterations += 1;
    }
    let elapsed = started.elapsed();
    println!(
        "retrieval_core dense: {iterations} scans, {:.0} vectors/s",
        iterations as f64 * DOCUMENTS as f64 / elapsed.as_secs_f64()
    );
}
