## 1. Baseline and Adoption Gates

- [x] 1.1 Record the current focused test, OpenSpec, code-intel, and scoped/root Sentrux baselines without overwriting unrelated dirty changes.
- [x] 1.2 Create the pinned open-source adoption record covering Xberg, Docling Core/Graph, GraphRAG, KAG, HanLP, PaddleNLP, Stanza, LTP, DeepKE, Splink, PROV, and OpenLineage.
- [x] 1.3 Implement format capability probes for Xberg TXT, HTML, EPUB, native PDF, and scanned PDF outputs, recording native IDs, offsets, nodes, elements, pages, geometry, relationships, and reading order.
- [x] 1.4 Decide from measured probes whether Docling Core is required as an optional structural fallback; do not add the dependency without a passing adoption record.

## 2. Source Plane Red Tests

- [x] 2.1 Add failing tests for exact normalized range reachability, including paragraph separators and other gaps.
- [x] 2.2 Add failing tests for repeated text, partial-element projection, and simultaneous Xberg nodes plus elements.
- [x] 2.3 Add failing tests for stable parent/children/previous/next traversal, explicit reading order, and table/figure/caption identities.
- [x] 2.4 Add failing tests proving semantic backend failure cannot reduce source reachability.

## 3. Complete Source Plane

- [x] 3.1 Add versioned source range/gap and source element records while preserving existing `AnchoredTextUnit` compatibility.
- [x] 3.2 Extend deterministic unitization so every normalized range resolves to a unit or explicit range record and exact text reconstruction is verified.
- [x] 3.3 Preserve backend-native identity, raw payload handles, projection status, element kind, page/geometry, and available structural relationships.
- [x] 3.4 Build and validate a versioned Source Plane coverage manifest separating range, element, structure, and capability coverage.
- [x] 3.5 Persist original ingested bytes as an addressable source-root element and bind file-backed document identity to the source digest, including extraction-empty scanned documents.
- [x] 3.6 Version the aggregate complete Source Plane separately from historical text-unit-only unitization and bind cursors/readers to the exact schema.
- [x] 3.7 Reject parent/neighbor cycles, multiple roots, and source-element subgraphs that are not reachable from the source-document root.

## 4. Xberg Structural Projection

- [x] 4.1 Consume Xberg nodes and elements cumulatively and deduplicate them by native identity rather than selecting one collection.
- [x] 4.2 Replace uniqueness-only exact-text projection with native reference/offset/order evidence and occurrence-aware fallback.
- [x] 4.3 Materialize deterministic parent/children/previous/next, heading trail, reading order, page, table, figure, and caption references when exposed.
- [x] 4.4 Record ambiguous or unavailable projections fail-empty with provenance and capability diagnostics.

## 5. Structural SourceIndex

- [x] 5.1 Extend the rebuildable SourceIndex with range, ordinal, section, heading, element, page, and lexical locator projections.
- [x] 5.2 Add deterministic neighbor, parent/child, ordered-range, and source-to-knowledge navigation APIs while retaining existing knowledge↔unit mappings.
- [x] 5.3 Add closure validation proving every index identity resolves to a Source Plane or canonical object and unknown references fail empty.
- [x] 5.4 Add an end-to-end unknown native-element candidate test that retains diagnostics and creates no fabricated source edge.
- [x] 5.5 Carry valid element-only grounding through canonical ArticleGraph objects, bidirectional SourceIndex projections, StageView, and provenance without fabricating text-unit IDs.
- [x] 5.6 Validate closure for every SourceIndex projection, including section, heading, page, lexical, hierarchy, range, element, unit, and knowledge directions, with corruption tests.

## 6. Bounded Stage Navigation

- [x] 6.1 Add a versioned CoverageManifest that separates source, visited, selected, serialized, presented, cited, critical, and omitted coverage.
- [x] 6.2 Add integrity-bound continuation cursors for deterministic paged traversal over document revision, policy, schema, and index digests.
- [x] 6.3 Implement the rescue ladder from initial selection through neighbor/parent/child expansion, targeted retrieval, and section-complete paging.
- [x] 6.4 Enforce the hard budget against the final serialized StageRequest, including StageView, anchors, retrieval hits, upstream claims, external evidence, metadata, and request provenance.
- [x] 6.5 Split oversized text and non-text source items deterministically with derived provenance or return explicit blocking records; forbid silent omission.
- [x] 6.6 Remove any fallback that requires full-document injection when the document exceeds the hard budget.
- [x] 6.7 Integrate continuation, targeted rescue, and section-complete paging into the application/provider runtime so persisted runs can resume beyond page one.
- [x] 6.8 Extend bounded traversal and coverage from text units to range/gap records and non-text source elements, including image-only scanned documents.
- [x] 6.9 Measure and revalidate the complete provider input envelope with a recorded exact tokenizer or conservative upper-bound counter, including provider instructions and response schema.
- [x] 6.10 Preserve incomplete coverage, continuation, and blocking state when a stage candidate arrives before bounded traversal is exhausted; do not mark the stage fully settled.
- [x] 6.11 Admit external evidence only through typed StageView selection and provenance; forbid direct EvidencePacket bypass.
- [x] 6.12 Account for unit, range, and element omissions and critical coverage end to end, and expose actual child/typed structural relations to the provider.

## 7. AI and Provenance Boundaries

- [x] 7.1 Label semantic graph objects as source-grounded machine candidates and prevent them from being treated as final six-stage conclusions.
- [x] 7.2 Prevent stage outputs from being written back as source facts while preserving references from stage conclusions to source and graph identities.
- [x] 7.3 Add typed source-reference resolution and provenance-closure validation for all final provider-visible material through ledger events to Source Plane records.
- [x] 7.4 Define and enforce a versioned argument-locating candidate and relation taxonomy, including premise, conclusion, evidence, example, objection, qualification, support, refutation, causation, contrast, and qualification.
- [x] 7.5 Preserve deterministic canonical node/edge/claim confidence values, methods, ambiguity, and candidate/mention provenance through StageView.
- [x] 7.6 Carry admitted typed unit/range/element/graph-object citations through the provider schema, candidate settlement, persisted ReadingClaim, and provenance ledger without requiring a fabricated text anchor.

## 8. Linguistic Backend Bake-off

- [x] 8.1 Define a thin linguistic adapter benchmark for offset recovery, locating recall, throughput, latency, memory, code license, model license, and failure behavior.
- [x] 8.2 Attempt HanLP, PaddleNLP, and Stanza under the adoption/license gate; record blocked or failed candidates honestly, run LTP only as an authorization-compatible control, and keep DeepKE as schema/output reference.
- [x] 8.3 Adopt a default or optional backend only when its measured record satisfies the gate; otherwise preserve deterministic source-first operation without it.
- [x] 8.4 Record pinned repository/revision/license/adapter/capability provenance for every adopted or copied algorithm in build or artifact lineage.
- [x] 8.5 Integrate and verify a production-callable optional structural fallback for PDF/scan formats where Xberg exposes no structure.
- [x] 8.6 Move an admitted Chinese linguistic backend from benchmark-only code into a production adapter with pinned model/dependency provenance and explicit degradation.
- [x] 8.7 Integrate a production-callable semantic backend for the versioned argument-locating taxonomy, retaining claim-only fallback as an explicitly partial capability.
- [x] 8.8 Persist the adopted Docling runtime, model artifacts, model licenses, OCR configuration, and adapter capability scope in every build where the production fallback contributes.

## 9. Long-document Acceptance

- [x] 9.1 Assemble real TXT, HTML, native PDF, scanned PDF, and EPUB fixtures including repeated text, tables, figures, captions, missing structure, Chinese/English, and a 100,000+ character document.
- [x] 9.2 Verify complete source reachability and deterministic full traversal through bounded continuation for every corpus document.
- [x] 9.3 Report must-hit Recall@token-budget, critical-anchor miss rate, coverage dimensions, input tokens, fallback rate, page count, p50/p95 latency, peak memory, backend failures, and unresolved projections.
- [x] 9.4 Compare lexical, dense where enabled, hybrid, reranking where enabled, and source-coverage rescue under identical budgets without claiming an unmeasured fixed savings rate.
- [x] 9.5 Measure 100,000+ character artifact bytes, CAS unique bytes, deduplication ratio, rebuild reuse, build peak memory, and bounded/streaming reads for Source Plane, SourceIndex, ledger, and aggregate artifacts.

## 10. Validation and Migration

- [x] 10.1 Run focused Source Plane, Xberg, SourceIndex, StageView, provenance, stage, application, and provider regression tests.
- [x] 10.2 Semantically decode genuine historical immutable artifacts with internal digest/identity validation and verify new schema versions rebuild deterministically without rewriting history.
- [x] 10.3 Run strict OpenSpec validation and scoped ArticleGraph/Source Plane Sentrux rules and gates, then compare the root gate with the recorded pre-change baseline.
- [x] 10.4 Update architecture documentation with the final Source Plane → ArticleGraph locating signals → StageView traversal → six-stage AI boundary.
- [x] 10.5 Add genuine pre-v2 cursor and stage-navigation fixtures with digest validation and explicit resume or stale-rejection behavior.
- [x] 10.6 Reconcile architecture and audit documentation with the implemented complete Source Plane, production backends, bounded navigation, and six-stage AI boundary.
