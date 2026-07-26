## Why

Readwelt can run its deterministic six-stage workflow, but the stages still consume `SemanticAtlas` retrieval packets rather than a traceable article intermediate representation. The current ArticleGraph spike only rewraps document sections and cannot preserve extraction candidates, ambiguity, merge lineage, provenance, or knowledge-to-source navigation, so it must be replaced before Completion Engine work can safely continue.

## What Changes

- Introduce revision-aware `AnchoredTextUnit` records with exact source anchors, structural context, content hashes, and explicit coverage gaps.
- Introduce separate `LinguisticBackend` and `SemanticExtractionBackend` seams with capability, coverage, degradation, model, and license descriptors.
- Persist immutable `GraphExtraction` candidate artifacts; extraction backends never mutate the canonical graph.
- Replace the current ArticleGraph spike with deterministic canonicalization that preserves mentions and emits `MergeDecision`, `ConflictRecord`, and `MergeReport`.
- Add an append-only, content-addressed `ProvenanceLedger` that distinguishes explicit text, extraction, canonicalization, internal derivation, external research, and synthesis.
- Add a rebuildable bidirectional `SourceIndex` between knowledge objects and `AnchoredTextUnit` records.
- Expose one deep `ArticleGraphBuilder.build(snapshot, normalized_text, policy) -> ArticleGraphBuildResult` interface while keeping backend and canonicalization seams internal.
- Add budgeted, explainable `StageView` projections and migrate the six-stage engine incrementally, retaining `SemanticAtlas` only as a temporary locator fallback.
- **BREAKING**: remove the existing document/section-only ArticleGraph artifact schema after migration; its artifacts are treated as disposable spike output.

## Capabilities

### New Capabilities

- `anchored-text`: Lossless, revision-aware article text units and source coverage accounting.
- `pluggable-extraction`: Host-neutral linguistic and semantic extraction seams plus immutable raw candidate artifacts.
- `canonical-article-graph`: Deterministic identity, relation, and claim canonicalization with preserved ambiguity and merge lineage.
- `provenance-source-index`: Independent provenance ledger and rebuildable bidirectional knowledge-to-source projections.
- `stage-view-consumption`: Budgeted, explainable graph projections that can be consumed by the six reading stages.

### Modified Capabilities

None. This repository has no archived OpenSpec capability specifications yet.

## Impact

- Replaces `src/readwelt/article_graph/` spike models and builder.
- Adds article IR, extraction, provenance, canonicalization, source-index, and stage-view modules.
- Changes artifact manifests and `ReadweltApplicationService` build/load paths.
- Changes stage input preparation while preserving current external Agent/MCP/HTTP/CLI turn contracts.
- Does not add HanLP, LTP, DeepKE, embeddings, or a general LLM as a required dependency in this change.
