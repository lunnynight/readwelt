# ArticleGraph Agent Reading MVP Release Gates

## Purpose and Decision Rule

This document turns the product-level success criteria in `product-prd.md` into
auditable release gates. It defines targets, not current achievements. A release
candidate is **GO** only when every validity gate and every product gate below
passes on the same frozen candidate. A pilot, smoke test, or convenient single
document cannot satisfy a release gate.

The Evaluation Owner publishes the signed decision record. Each gate owner signs
their evidence section; the Product Owner makes the final GO/NO-GO decision but
cannot waive a failed grounding or experimental-validity gate. Changing a dataset,
metric, threshold, exclusion, or scoring rule after scored runs begin creates a new
benchmark version and requires all scored runs to be repeated.

## Owners

| Role | Accountability |
|---|---|
| Product Owner | Release scope, final decision, and product claims |
| Intake Owner | Xberg ingestion, extraction-quality classification, and recovery |
| Evidence Owner | ArticleGraph integrity, provenance, and fail-closed behavior |
| Query Owner | Public CLI/Python behavior, budgets, determinism, and continuations |
| Reading Owner | Six-stage adoption, receipts, and agent-visible context |
| Evaluation Owner | Preregistration, matched A/B execution, scoring, uncertainty, and report |
| Runtime Owner | Concurrency, latency, resource bounds, and fault recovery |

One person may fill multiple roles, but every evidence artifact records the named
owner and reviewer for that release candidate.

## Frozen Datasets and Workloads

### D1: Scored real-document corpus

- Source: the real `“海量”专题` corpus.
- Size: at least 24 immutable PDFs and at least 72 scored tasks.
- Stratification: at least three subject categories, two length bands, and two
  extraction-quality bands, with at least two documents in every represented
  category-by-length-by-quality cell.
- Each manifest entry records the source SHA-256, selection stratum, extraction
  quality, gold anchors, tasks, scoring rubric, and exclusions before scored runs.
- Every document contributes location, evidence/citation, and comprehension tasks.
  A document may be excluded only by a preregistered rule; attempted and excluded
  documents remain visible in the report.

### D2: Contract and corruption suite

- Versioned schema fixtures, legacy ArticleGraph artifacts, missing-locator cases,
  dangling references, corrupted continuations, changed snapshots, and exhausted
  budget cases.
- Includes representative Xberg-produced Chinese research documents and does not
  require embeddings or a graph database.

### D3: Clean-room usability suite

- At least 10 task attempts started from the installed CLI help and Python public
  package surface only.
- The agent receives no repository map, internal artifact layout, private command,
  or implementation hint.

### D4: Operational workload

- The frozen D1 snapshots queried at concurrency 1, 4, and 8 with a fixed mix of
  `search`, `locate`, `evidence`, `neighbors`, `trace_claim`, and `expand_context`.
- Includes concurrent ingestion/query isolation, process interruption, retry, and
  continuation-after-snapshot-change cases.
- Hardware, OS, dependency versions, cache state, worker count, and workload seed
  are recorded with the result.

## Experimental Validity Gates

| ID | Owner | Dataset | Pass threshold | Required evidence |
|---|---|---|---|---|
| V1 Preregistration | Evaluation Owner | D1 | Manifest, hypotheses, metrics, thresholds, exclusions, seeds, and analysis code digest are frozen before the first scored run; zero post-hoc mutations | `manifest.json`, `preregistration.json`, digests, timestamps |
| V2 Matched pairs | Evaluation Owner | D1 | 100% of accepted pairs match document, task, model, model settings, answer schema, wall-clock policy, and execution policy; infrastructure exposure is the only declared treatment difference | pair configuration diff and run metadata |
| V3 Proven treatment use | Reading Owner | D1 | 100% of scored treatment runs contain direct ArticleGraph tool-trajectory events and matching stored receipts; 100% of scored runs contain a parseable final answer | trajectories, receipts, final-answer records, validity report |
| V4 Complete accounting | Evaluation Owner | D1 | At least 95% of attempted pairs are valid and all invalid, timed-out, excluded, or failed attempts are reported; every valid pair has complete timing, token, evidence-volume, and infrastructure-cost fields | attrition report and telemetry completeness report |

If any validity gate fails, no baseline-versus-treatment winner or product-improvement
claim may be published, even if point estimates look favorable.

## Product Release Gates

| ID | Criterion and owner | Dataset | Pass threshold | Required evidence artifact |
|---|---|---|---|---|
| G1 Coverage | Coverage — Intake Owner | D1 | At least 95% of attempted documents produce a queryable immutable snapshot; at least 99% of preregistered valid query requests complete without an untyped error; 100% of degraded locator precision and failures are explicitly classified | `coverage-report.json`, ingestion manifests, failure ledger |
| G2 Grounding | Grounding — Evidence Owner | D1 + D2 | 100% of returned claims and relations resolve to existing graph objects and source evidence; 100% of dangling/unsupported references fail closed; citation precision is at least 0.95 and evidence-anchor recall is at least 0.90 on gold tasks | `grounding-report.json`, integrity results, scored evidence rows |
| G3 Location effectiveness | Task effectiveness — Evaluation Owner | D1 | Treatment macro location F1 exceeds baseline by at least 5 percentage points and the paired 95% bootstrap confidence interval for the delta has a lower bound above 0 | `effectiveness-report.json`, paired score rows, bootstrap samples |
| G4 Comprehension effectiveness | Task effectiveness — Evaluation Owner | D1 | Treatment rubric-normalized comprehension exceeds baseline by at least 5 percentage points and the paired 95% bootstrap confidence interval for the delta has a lower bound above 0; citation correctness is at least 0.95 and is not lower than baseline by more than 2 points | `effectiveness-report.json`, blinded judgments, adjudication log |
| G5 Warm repeated-task efficiency | Efficiency — Reading Owner | D1 | Against the matched raw baseline, treatment reduces median agent-visible source bytes by at least 30% and median model input tokens by at least 20%; warm end-to-end p95 latency is no more than 10% slower; cold build, warm query, and 3-task amortized costs are reported separately | `efficiency-report.json`, model usage, evidence exposure, cold/warm timings |
| G6 Public-surface usability | Usability — Query Owner | D3 | At least 90% of attempts discover the supported operation and produce a schema-valid answer without reading internal layouts; median time to first valid query is at most 5 minutes; no attempt requires an undocumented command | `usability-report.json`, help capture, trajectories, answers |
| G7 Replayability | Reproducibility — Query Owner | D1 + D2 | 100% of sampled scored runs replay against the recorded immutable snapshot with the same normalized request digest, ordered object IDs, truncation reason, and receipt digest; a changed snapshot produces the typed restart-required error in 100% of cases | `replay-report.json`, snapshots, requests, receipts, replay logs |
| G8 Operational fitness | Operational fitness — Runtime Owner | D4 | No corruption, cross-snapshot leakage, deadlock, or silent partial result; deterministic result digests match concurrency-1 output in 100% of runs; warm query p95 is at most 2 s and p99 at most 5 s on recorded reference hardware; interrupted ingestion recovers or fails explicitly in 100% of injected cases | `operational-report.json`, resource series, fault-injection and recovery logs |
| G9 Compatibility and rollback | Operational fitness — Product Owner | D2 | 100% of versioned legacy artifacts parse through the compatibility path; legacy `StageView` consumers pass their regression suite; rollback procedure completes successfully from a clean project copy | `compatibility-report.json`, regression results, rollback transcript |

## Evidence Bundle Contract

Evidence for one candidate is stored under a content-addressed directory such as
`reports/articlegraph-agent-reading/<candidate-digest>/` and contains:

1. `release-decision.json` with candidate digest, code revision, artifact schema
   versions, owners, reviewers, and the result of V1-V4 and G1-G9.
2. The frozen D1-D4 manifests and every required report named above.
3. Raw paired run records, parseable final answers, direct tool trajectories, query
   receipts, model usage, exposed evidence, timing, and failure records.
4. Immutable ArticleGraph/source snapshot digests and enough configuration to replay
   every sampled result without relying on an unrecorded local path.
5. Exact commands, dependency lock digests, environment metadata, and logs for tests,
   lint, type checking, Code Intel, Sentrux, and rollback verification.

The summary report links to underlying rows and receipts. Missing evidence is a gate
failure; it is never represented as zero, success, or “not applicable” unless the
preregistered protocol explicitly permits that value.

## Claim Policy

- “Evidence-grounded” requires G2.
- “Locates more accurately” requires G3.
- “Understands better” requires G4.
- “Cheaper for repeated reading” requires G5 and must state the cold/warm/amortized
  assumption.
- “Reproducible” requires G7.
- “Ready for the ArticleGraph Agent Reading MVP” requires V1-V4 and G1-G9 together.

Per-metric results, uncertainty, failures, attrition, and costs remain visible even
when the candidate passes. A later release may revise thresholds only through a new
version of this contract before its scored runs begin.
