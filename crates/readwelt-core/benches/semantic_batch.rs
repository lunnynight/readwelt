use std::{
    hint::black_box,
    time::{Duration, Instant},
};

use readwelt_core::analyze_segments;

fn main() {
    let documents: Vec<String> = (0..500)
        .map(|ordinal| format!("第{ordinal}段：知识图谱用于语义检索与文章分析。"))
        .collect();
    let started = Instant::now();
    let mut iterations = 0_u64;
    while started.elapsed() < Duration::from_millis(750) {
        black_box(analyze_segments(black_box(&documents), 0.82));
        iterations += 1;
    }
    let elapsed = started.elapsed();
    let documents_per_second = documents.len() as f64 * iterations as f64 / elapsed.as_secs_f64();
    println!(
        "semantic_batch: {iterations} iterations, {:.0} documents/s",
        documents_per_second
    );
}
