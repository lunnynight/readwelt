## 1. Product Contract and Query Contracts

- [x] 1.1 Convert the product-level success criteria into measurable release gates with owners, datasets, thresholds, and evidence artifacts
- [x] 1.2 Define versioned query-operation, filter, budget, hit, evidence-envelope, page, receipt, continuation, and typed-error schemas
- [x] 1.3 Add schema tests for nullable locator precision, provenance integrity, serialization stability, and backward-compatible parsing
- [x] 1.4 Document the public operation semantics and explicitly map existing `StageView` fields into the new result envelope

## 2. Core Query Service

- [x] 2.1 Extend `SourceIndex` with deterministic exact and lexical candidate retrieval across source units, nodes, claims, and relations
- [x] 2.2 Implement locate and evidence resolution with fail-closed source-reference validation
- [x] 2.3 Implement bounded neighbors and claim-trace traversal with stable ordering and relation paths
- [x] 2.4 Implement bounded context expansion and versioned snapshot/query-bound continuation tokens
- [x] 2.5 Add unit and property tests for all budgets, truncation reasons, continuation invariants, missing locators, and dangling references

## 3. Public Interfaces

- [x] 3.1 Add one ArticleGraph CLI command family for all query operations with JSON output and stable exit/error contracts
- [x] 3.2 Add the Python query-service entry point over persisted graph artifacts and source indexes
- [x] 3.3 Add CLI/Python parity tests proving equivalent normalized requests return equivalent ordered results
- [x] 3.4 Add end-to-end fixtures using representative Xberg-produced Chinese research PDFs without requiring embeddings or a graph database

## 4. Six-Stage Reading Integration

- [x] 4.1 Define per-stage allowed query intents, default budgets, and query-receipt persistence
- [x] 4.2 Migrate one reading stage from eager `StageView` consumption to the query service and run parity/budget tests
- [x] 4.3 Migrate the remaining stages while retaining the compatibility adapter until regression tests pass
- [x] 4.4 Measure and document per-stage context exposure before and after migration without claiming quality gains prematurely

## 5. Controlled Evaluation

- [x] 5.1 Build a preregistered stratified manifest from `“海量”专题` with immutable document digests, gold anchors, tasks, rubrics, and exclusions
- [ ] 5.2 Enforce matched baseline/treatment configuration and persist model usage, timing, tool trajectories, exposed evidence, query receipts, and final answers
- [ ] 5.3 Implement validity gates for missing treatment use, mismatched receipts, unparseable answers, context failure, and incomplete cost telemetry
- [ ] 5.4 Report location, citation, comprehension, latency, tokens, failures, and cold/warm/amortized infrastructure costs separately
- [ ] 5.5 Run a non-scored pilot, freeze any justified protocol corrections, then run the scored stratified A/B evaluation

## 6. Quality and Architecture Verification

- [ ] 6.1 Run focused tests, full test suite, formatter/linter, and type checker; record reproducible commands and results
- [ ] 6.2 Run the mandated local Code Intel Pipeline and Sentrux architecture/rule/test-gap checks, resolving real `graph_missing` debt through the emitted Understand Anything command if present
- [ ] 6.3 Update ArticleGraph architecture and user documentation with the Build, Source, Provenance, Query, and six-stage consumption boundaries
- [ ] 6.4 Verify existing graph artifacts and legacy `StageView` consumers remain usable for rollback
