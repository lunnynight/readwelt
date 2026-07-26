# Retrieval Benchmark

The retrieval benchmark is an implementation-neutral acceptance surface for
Readwelt's evidence selection. It is not a RAG benchmark and it does not prescribe
BM25, BM25+, BM25L, BM25F, dense retrieval, or a fusion algorithm.

## Fixture contract

`benchmarks/retrieval/zh_seed_v1.json` contains independent query cases. Each case
has a query and a small candidate corpus of anchored passages. An anchor carries:

- a stable `anchor_id`;
- `section_id` and `section_title`, even when a backend ignores fields;
- body `text`;
- an integer relevance grade from 0 through 3.

A backend must return every candidate exactly once as `(anchor_id, score)`, ordered
best-first. This complete-ranking rule makes metric changes auditable and catches
silent filtering differences between implementations.

The seed fixture is explicitly marked `synthetic_seed`. It exists to expose known
failure modes cheaply:

- Chinese semantic paraphrase;
- exact model names, people, and numeric values;
- long relevant passages competing with short keyword matches;
- evidence carried by section titles;
- high lexical-overlap negatives and reversed numbers.

It must not be reported as evidence of production quality. A future
`real_corpus` fixture should be sampled from licensed or user-provided articles,
judged independently by at least two readers, and versioned separately.

## First real-corpus acceptance run

A user-provided Chinese EPUB, *第一性原理* by 李善友, is used locally and is
not committed to the repository. Xberg extracted 99,415 characters and 901
paragraph anchors. EPUB NCX enrichment recovered 64 body titles plus one
frontmatter group.

The first automatic acceptance task uses each NCX title as a query, excludes
heading blocks from 747 body candidates, and treats paragraphs belonging to the
same NCX section as relevant. This is a real-corpus **section-navigation**
benchmark with silver membership labels, not an independently judged semantic
relevance benchmark.

On the local Windows release build at `k=10`:

| scorer | Hit@10 | MRR | nDCG@10 | macro Recall@10 |
|---|---:|---:|---:|---:|
| BM25 | 0.8906 | 0.6349 | 0.3618 | 0.3063 |
| BM25+ | 0.9062 | 0.6239 | 0.3607 | 0.3056 |
| BM25L | 0.7656 | 0.5246 | 0.2910 | 0.2518 |

BM25+ therefore has a small coverage advantage on this task, while BM25 places
the first relevant paragraph slightly earlier. The provisional BM25+ default is
a coverage-first policy; these results do not establish universal superiority.
Paraphrase queries and independent human judgments remain necessary before
selecting tokenizer or dense-retrieval policy.

## Metrics and timing

The harness reports macro Recall@k, MRR, and graded nDCG@k overall and by category.
Recall and MRR treat every grade above zero as relevant; nDCG preserves grades.
It also reports p50/p95 query latency and throughput. Latency is measured around
backend `rank` only, after configurable warmups.

Output uses a versioned, sorted JSON structure. Ranking and quality fields are
deterministic; timing values naturally vary by machine and run.

Run the compatibility path and all reusable native scorers:

```powershell
uv run python -m benchmarks.retrieval.run `
  --backend current-bm25 `
  --backend native-bm25 `
  --backend bm25-plus `
  --backend bm25-l `
  --output .readwelt/benchmarks/retrieval.json
```

`current-bm25` intentionally rebuilds the compatibility index for every query.
The three native backends reuse a built index, matching production v2. On the
synthetic seed all four currently score Recall@3 0.85, MRR 0.7917, and nDCG@3
0.6693. This result establishes regression parity only; it does not establish
that any scorer is best on real Chinese articles.

Compare it with another implementation by exposing an object or zero-argument
factory with `name: str` and `rank(case)`:

```powershell
uv run python -m benchmarks.retrieval.run `
  --backend current-bm25 `
  --backend my_package.benchmarks:CandidateBackend
```

The custom backend receives the benchmark `BenchmarkCase`, so it may index body
text only or deliberately use fields such as `section_title`. No production
module imports benchmark code.
