# ArticleGraph Long-document Acceptance

- Acceptance: PASS
- Token budget: 4096
- Hard serialized budget: 16384
- Counter: `readwelt.utf8_bytes.max_1_token_per_byte.v1` (conservative_upper_bound)
- Report digest: `sha256:ea46e7e1e081faf33bb7648375d06c6c221649c13623e52219158d5db5fce880`

The input-token values are measured with the declared counter. This run uses a conservative upper bound, not a provider tokenizer.

## Source reachability and traversal

| Case | Format | Units | Ranges | Elements | Source root | Complete | Pages | Input tokens | p50 ms | p95 ms | Peak bytes | Backend failures | Unresolved |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| kag-zhou-xingchi-zh-txt | txt | 1.000 | 1.000 | 1.000 | 1.000 | True | 1 | 4621 | 11.915 | 11.915 | 134458 | 19 | 2 |

## Equal-budget retrieval controls

| Case | Strategy | Enabled | Recall | Critical miss | Input tokens | Pages | Latency ms | Peak bytes | Fallback | Reason |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| kag-zhou-xingchi-zh-txt | full_text | False | 0.000 | 1.000 | 110 | 1 | 0.047 | 20782 | 0.000 | full_text_exceeds_identical_token_budget |
| kag-zhou-xingchi-zh-txt | lexical | True | 0.000 | 1.000 | 110 | 1 | 0.520 | 157229 | 0.000 |  |
| kag-zhou-xingchi-zh-txt | dense | False | 0.000 | 1.000 | 110 | 1 | 0.018 | 930 | 0.000 | dense_backend_not_enabled |
| kag-zhou-xingchi-zh-txt | hybrid | False | 0.000 | 1.000 | 110 | 1 | 0.015 | 930 | 0.000 | dense_backend_not_enabled_for_hybrid |
| kag-zhou-xingchi-zh-txt | reranking | False | 0.000 | 1.000 | 110 | 1 | 0.016 | 930 | 0.000 | reranking_backend_not_enabled |
| kag-zhou-xingchi-zh-txt | source_coverage_rescue | True | 1.000 | 0.000 | 4621 | 1 | 0.009 | 984 | 0.000 |  |
