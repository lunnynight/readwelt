## Why

The completed ArticleGraph foundation proves that Readwelt can build anchored units, provenance, canonical graph objects, source indexes, and stage views, but it does not yet guarantee that a long document remains completely addressable and progressively traversable without full-text injection. ArticleGraph must be hardened as a preprocessing and navigation substrate for AI—not as a substitute for the six-stage AI reading process—and implementation must prefer proven open-source components over bespoke replacements.

## What Changes

- Define a complete Source Plane in which every source range and non-text source element has a stable retrieval identity, deterministic reading position, and provenance, even when higher-level structure or semantic extraction is unavailable.
- Add source-first structural, ordinal, range, and lexical navigation that does not depend on successful entity, relation, or claim extraction.
- Replace one-shot StageView selection with hard-budget, resumable navigation that reports selected and omitted material, supports structural and neighborhood expansion, and never treats silent omission as complete coverage.
- Make semantic graph objects explicitly advisory locating candidates; they cannot become six-stage conclusions or be written back as source facts.
- Add an open-source adoption gate requiring source, license, model-license, capability, and pinned-revision evaluation before implementing parsers, structure projection, provenance, retrieval, or linguistic extraction in-house.
- Add real long-document acceptance covering native and scanned PDF, EPUB, HTML, TXT, repeated text, tables, figures, captions, missing structure, and documents over 100,000 Chinese characters.
- **BREAKING**: `coverage_complete` can no longer mean only that the build/index succeeded; source coverage, view presentation coverage, critical-anchor coverage, and semantic capability coverage become separate states.
- **BREAKING**: full-document prompt injection is removed as the normal fallback for incomplete semantic extraction or exhausted StageView budgets.

## Capabilities

### New Capabilities

- `article-source-plane`: Complete source preservation, stable addressing, deterministic traversal, structural projection, and source-first indexes.
- `bounded-stage-navigation`: Hard-budget StageView paging, continuation cursors, coverage manifests, rescue traversal, and AI/output boundaries.
- `articlegraph-backend-adoption`: Open-source capability and license evaluation, thin adapters, pinned provenance, and build-versus-buy decisions.
- `long-document-navigation-benchmark`: Corpus, metrics, and acceptance gates for complete and efficient long-document navigation.

### Modified Capabilities

None in this change. The prior foundation change is complete but not yet archived into baseline specs; these new capabilities supersede any conflicting fallback or completeness behavior without rewriting that change's historical artifacts.

## Impact

- Primary code: `src/readwelt/runner`, `src/readwelt/domain`, `src/readwelt/article_ir`, `src/readwelt/provenance`, `src/readwelt/article_graph`, and `src/readwelt/stage_views`.
- Stage and provider contracts gain explicit continuation, omission, coverage, and serialized-input budget fields.
- Xberg remains the primary ingestion backend; Docling Core/Graph, GraphRAG, KAG, HanLP/PaddleNLP/Stanza, LTP, DeepKE, Splink, PROV, and OpenLineage are evaluated only at the narrow reuse boundaries documented by this change.
- Tests and fixtures expand to real PDF/EPUB inputs and 100,000+ character traversal scenarios.
- Existing dirty worktree changes must be preserved and reconciled; artifact deduplication and provider work remain subordinate to Source Plane correctness.
