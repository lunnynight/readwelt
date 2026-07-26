## 1. Article IR and Anchoring

- [x] 1.1 Replace the spike document/section graph wrappers with revision-aware `AnchoredTextUnit`, source-reference, structure, and coverage models.
- [x] 1.2 Implement deterministic snapshot unitization with exact plain-text coverage and explicit unsupported/uncovered records.
- [x] 1.3 Preserve available Xberg structure and capability gaps without fabricating unavailable layout data.

## 2. Extraction Contracts and Artifacts

- [x] 2.1 Define backend descriptors, capability enums, per-capability outcomes, and normalized degradation reports.
- [x] 2.2 Define separate `LinguisticBackend` and `SemanticExtractionBackend` protocols and registries.
- [x] 2.3 Implement immutable `GraphExtraction` candidate artifacts and deterministic built-in fallback backends.

## 3. Canonical Graph and Trust Plane

- [x] 3.1 Define canonical nodes, edges, epistemic statuses, merge decisions, conflicts, and merge reports.
- [x] 3.2 Implement deterministic identity resolution, relation reconciliation, and claim assembly while preserving mentions.
- [x] 3.3 Implement append-only content-addressed `ProvenanceLedger` events and chain verification.
- [x] 3.4 Implement rebuildable bidirectional `SourceIndex` projections after canonicalization.

## 4. Deep Build Interface and Persistence

- [x] 4.1 Implement `ArticleGraphBuilder.build(snapshot, normalized_text, policy) -> ArticleGraphBuildResult` as the application-facing interface.
- [x] 4.2 Version and digest every artifact in the invalidation chain.
- [x] 4.3 Replace spike persistence and manifest integration without disturbing external Agent turn contracts.

## 5. StageView Consumption

- [x] 5.1 Define `StageContext`, `StageView`, selection reasons, coverage summary, missing capabilities, and token accounting.
- [x] 5.2 Implement StageView projection with knowledge-to-source traversal and labeled SemanticAtlas fallback.
- [x] 5.3 Migrate Stage 1 to consume StageView and then migrate Stages 2-6 through the same interface.

## 6. Engineering Verification

- [x] 6.1 Verify source coverage, provenance closure, epistemic separation, deterministic rebuilds, and bidirectional index integrity.
- [x] 6.2 Run existing regression tests and static checks, repairing only failures caused by this change.
- [x] 6.3 Run OpenSpec validation and Sentrux architectural rules, then update completed task checkboxes.
