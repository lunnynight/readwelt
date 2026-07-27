# ArticleGraph Long-document Acceptance

- Acceptance: PASS
- Token budget: 512
- Hard serialized budget: 16384
- Counter: `readwelt.utf8_bytes.max_1_token_per_byte.v1` (conservative_upper_bound)
- Report digest: `sha256:25b905202e73d70f5d8ef52fa2a53f60b052ab9a0d1d3472591ca30e930a7622`

The input-token values are measured with the declared counter. This run uses a conservative upper bound, not a provider tokenizer.

## Source reachability and traversal

| Case | Format | Units | Ranges | Elements | Source root | Structure closed | Complete | Pages | Input tokens | p50 ms | p95 ms | Peak bytes | Backend failures | Unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| graphrag-dulce-en-txt | txt | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 19 | 190716 | 62.196 | 312.992 | 2266020 | 2 | 94 |
| kag-zhou-xingchi-zh-txt | txt | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 4 | 17452 | 10.558 | 14.378 | 84692 | 2 | 2 |
| docling-arxiv-2206-01062-en-html | html | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 27 | 228322 | 37.131 | 250.812 | 992224 | 2 | 77 |
| kag-knowledge-graph-tutorial-native-pdf | native_pdf | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 167 | 2406935 | 1788.532 | 2265.703 | 13934151 | 2 | 1877 |
| docling-graph-image-only-scanned-pdf | scanned_pdf | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 1 | 3304 | 9.695 | 9.695 | 51779 | 3 | 2 |
| first-principles-zh-epub | epub | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 106 | 1342531 | 781.842 | 1116.001 | 10285414 | 2 | 902 |
| gutenberg-water-margin-zh-epub | epub | 1.000 | 1.000 | 1.000 | 1.000 | True | True | 372 | 3739279 | 563.661 | 1824.271 | 12462306 | 2 | 1828 |

## Equal-budget retrieval controls

| Case | Strategy | Enabled | Recall | Critical miss | Input tokens | Pages | Latency ms | Peak bytes | Fallback | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| graphrag-dulce-en-txt | full_text | False | 0.000 | 1.000 | 0 | 1 | 0.141 | 5482 | 0.000 | full_text_exceeds_identical_token_budget |
| graphrag-dulce-en-txt | lexical | True | 1.000 | 0.000 | 5902 | 1 | 4.234 | 93915 | 0.000 |  |
| graphrag-dulce-en-txt | dense | False | 0.000 | 1.000 | 0 | 1 | 0.002 | 0 | 0.000 | dense_backend_not_enabled |
| graphrag-dulce-en-txt | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| graphrag-dulce-en-txt | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| graphrag-dulce-en-txt | source_coverage_rescue | True | 1.000 | 0.000 | 190716 | 19 | 0.015 | 11736 | 0.000 |  |
| kag-zhou-xingchi-zh-txt | full_text | False | 0.000 | 1.000 | 0 | 1 | 0.022 | 20782 | 0.000 | full_text_exceeds_identical_token_budget |
| kag-zhou-xingchi-zh-txt | lexical | True | 1.000 | 0.000 | 827 | 1 | 1.054 | 157229 | 0.000 |  |
| kag-zhou-xingchi-zh-txt | dense | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled |
| kag-zhou-xingchi-zh-txt | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| kag-zhou-xingchi-zh-txt | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| kag-zhou-xingchi-zh-txt | source_coverage_rescue | True | 1.000 | 0.000 | 17452 | 4 | 0.007 | 984 | 0.000 |  |
| docling-arxiv-2206-01062-en-html | full_text | False | 0.000 | 1.000 | 0 | 1 | 0.128 | 8977 | 0.000 | full_text_exceeds_identical_token_budget |
| docling-arxiv-2206-01062-en-html | lexical | True | 1.000 | 0.000 | 5891 | 1 | 5.128 | 169964 | 0.000 |  |
| docling-arxiv-2206-01062-en-html | dense | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled |
| docling-arxiv-2206-01062-en-html | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| docling-arxiv-2206-01062-en-html | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.000 | 0 | 0.000 | reranking_backend_not_enabled |
| docling-arxiv-2206-01062-en-html | source_coverage_rescue | True | 1.000 | 0.000 | 228322 | 27 | 0.013 | 5592 | 0.000 |  |
| kag-knowledge-graph-tutorial-native-pdf | full_text | False | 0.000 | 1.000 | 0 | 1 | 0.926 | 77960 | 0.000 | full_text_exceeds_identical_token_budget |
| kag-knowledge-graph-tutorial-native-pdf | lexical | True | 1.000 | 0.000 | 6261 | 1 | 32801.403 | 1070399 | 0.000 |  |
| kag-knowledge-graph-tutorial-native-pdf | dense | False | 0.000 | 1.000 | 0 | 1 | 0.003 | 0 | 0.000 | dense_backend_not_enabled |
| kag-knowledge-graph-tutorial-native-pdf | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| kag-knowledge-graph-tutorial-native-pdf | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| kag-knowledge-graph-tutorial-native-pdf | source_coverage_rescue | True | 1.000 | 0.000 | 2406935 | 167 | 0.128 | 173016 | 0.000 |  |
| docling-graph-image-only-scanned-pdf | full_text | True | 1.000 | 0.000 | 0 | 1 | 0.021 | 784 | 0.000 |  |
| docling-graph-image-only-scanned-pdf | lexical | True | 1.000 | 0.000 | 0 | 1 | 0.013 | 784 | 0.000 |  |
| docling-graph-image-only-scanned-pdf | dense | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled |
| docling-graph-image-only-scanned-pdf | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| docling-graph-image-only-scanned-pdf | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| docling-graph-image-only-scanned-pdf | source_coverage_rescue | True | 1.000 | 0.000 | 3304 | 1 | 0.004 | 720 | 0.000 |  |
| first-principles-zh-epub | full_text | False | 0.000 | 1.000 | 0 | 1 | 0.870 | 39048 | 0.000 | full_text_exceeds_identical_token_budget |
| first-principles-zh-epub | lexical | True | 1.000 | 0.000 | 10047 | 1 | 21103.473 | 1403714 | 0.000 |  |
| first-principles-zh-epub | dense | False | 0.000 | 1.000 | 0 | 1 | 0.003 | 0 | 0.000 | dense_backend_not_enabled |
| first-principles-zh-epub | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| first-principles-zh-epub | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| first-principles-zh-epub | source_coverage_rescue | True | 1.000 | 0.000 | 1342531 | 106 | 0.088 | 74712 | 0.000 |  |
| gutenberg-water-margin-zh-epub | full_text | False | 0.000 | 1.000 | 0 | 1 | 2.723 | 77960 | 0.000 | full_text_exceeds_identical_token_budget |
| gutenberg-water-margin-zh-epub | lexical | True | 1.000 | 0.000 | 11545 | 1 | 76473.565 | 5794307 | 0.000 |  |
| gutenberg-water-margin-zh-epub | dense | False | 0.000 | 1.000 | 0 | 1 | 0.003 | 0 | 0.000 | dense_backend_not_enabled |
| gutenberg-water-margin-zh-epub | hybrid | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | dense_backend_not_enabled_for_hybrid |
| gutenberg-water-margin-zh-epub | reranking | False | 0.000 | 1.000 | 0 | 1 | 0.001 | 0 | 0.000 | reranking_backend_not_enabled |
| gutenberg-water-margin-zh-epub | source_coverage_rescue | True | 1.000 | 0.000 | 3739279 | 372 | 0.131 | 173044 | 0.000 |  |
