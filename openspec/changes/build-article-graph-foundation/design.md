## Context

Readwelt's current runtime imports documents through Xberg, creates a `SourceDocumentSnapshot`, builds a `SemanticAtlas`, and prepares retrieval packets for six deterministic reading stages. A recently added ArticleGraph spike is persisted but never consumed; it models only document, section, and source-span wrappers.

The foundation must support long documents without repeatedly sending the full source to an AI, while never confusing author statements with system inference or later completion. Open-source research supports borrowing document provenance patterns from Docling, bidirectional TextUnit indexes from GraphRAG/KAG, optional comparison and clustering ideas from Splink, the W3C PROV vocabulary, and versioned event envelopes from OpenLineage. None of those projects supplies Readwelt's product-specific ArticleGraph, merge semantics, StageView, or Completion Engine.

## Goals / Non-Goals

**Goals:**

- Preserve exact, revision-aware source anchors and account for source coverage.
- Make extraction backends replaceable and degradable without coupling stages to vendors.
- Preserve raw extraction candidates, uncertainty, conflicts, and every canonicalization decision.
- Provide a canonical graph whose nodes and edges can always be traced to source units or explicit derivations.
- Give every stage a minimal, budgeted, explainable view instead of an opaque retrieval packet.
- Keep one deep build interface for application callers.

**Non-Goals:**

- Selecting or installing HanLP, LTP, DeepKE, or another heavy model.
- Replacing Xberg.
- Making dense retrieval or retrieval quality the product benchmark.
- Implementing CompletionPlan, external research, gap completion, counterfactual analysis, or transferable-principle generation.
- Treating W3C PROV, OpenLineage, GraphRAG, KAG, or Splink as the core runtime.

## Decisions

### 1. One deep ArticleGraph build module

Application code calls:

```python
ArticleGraphBuilder.build(
    snapshot: SourceDocumentSnapshot,
    normalized_text: str,
    policy: ArticleGraphBuildPolicy,
) -> ArticleGraphBuildResult
```

The caller resolves `snapshot.normalized_text_ref` and supplies the bytes as text; the builder verifies them against `snapshot.content_digest`. The result contains text units, raw extractions, graph, ledger, merge report, source index, and capability report. Backend registry, extraction ordering, canonicalization, and projection construction remain implementation details. This avoids seven shallow public modules that every caller must orchestrate.

Alternative rejected: exposing each pipeline step directly to application and stage callers. That spreads ordering, degradation, and consistency rules across the repository.

### 2. Immutable facts versus rebuildable projections

The durable factual record consists of the source snapshot, anchored units, raw extractions, merge decisions/conflicts, and provenance events. `ArticleGraph`, `SourceIndex`, and `StageView` are deterministic, versioned projections that can be rebuilt when schema or policy changes.

Alternative rejected: treating the canonical graph or source index as the only source of truth. That would lose rejected candidates and make policy upgrades unauditable.

### 3. Explicit epistemic status

Every knowledge assertion and provenance event records one of:

- `explicit`
- `linguistic_inference`
- `semantic_inference`
- `canonicalized`
- `internal_derived`
- `external`
- `synthesized`

The foundation produces only the first four. Later Completion Engine outputs may use the remaining statuses but MUST NOT be represented as author-explicit content.

### 4. Anchoring and coverage are invariants

An `AnchoredTextUnit` includes document and revision identity, structural path, ordinal, kind, exact text, content hash, parent/previous/next references, heading trail, and one or more source references. Source references may include character ranges, pages, bounding boxes, Xberg element references, or stable textual anchors.

All non-whitespace source content MUST either be covered by a text unit or represented in an uncovered/unsupported coverage record. Normalization transformations MUST be recorded.

### 5. Linguistic and semantic extraction are separate seams

`LinguisticBackend` provides sentence, token, POS, NER, dependency, SRL, and coreference capabilities. `SemanticExtractionBackend` provides entity, relation, event, concept, claim, evidence, example, objection, and qualification candidates.

Backends declare identity, version, model revision, supported capabilities, required resources, license metadata, network behavior, and determinism. Per-capability outcomes distinguish `unsupported`, `not_run`, `empty`, `failed`, `partial`, and `complete`.

An absent or failed optional backend degrades the capability report and does not fail document import.

### 6. Raw extraction is immutable

Each backend invocation emits a `GraphExtraction` artifact containing candidate nodes and edges, source references, confidence, ambiguity, unresolved references, warnings, backend descriptor, input unit IDs, and schema version. Backends never write canonical nodes or edges.

### 7. Canonicalization is deterministic and non-destructive

Canonicalization runs in three ordered phases:

1. identity resolution;
2. relation reconciliation;
3. claim assembly.

Each candidate comparison produces `merge`, `keep_separate`, `defer`, or `reject`. Mention nodes remain addressable after canonical entity creation. Unresolved ambiguity produces a conflict or deferred decision rather than an implicit LLM call.

The canonicalizer is a pure function of raw artifacts, policy, and schema version. Any future AI-assisted resolution must be a separately recorded resolver.

### 8. Provenance ledger is independent

The ledger is an append-only sequence of content-addressed events. Each event records sequence, event type, timestamp, producer/schema/model identity, inputs, outputs, source references, confidence, ambiguity, payload, and previous digest.

Grounding fails empty: a source-required knowledge object without a valid anchor is rejected or recorded as unresolved; the system does not invent a source. A W3C PROV export adapter may be added later, but the ledger does not depend on `prov`.

### 9. SourceIndex is a projection

The source index is materialized after canonicalization and contains at least:

- node to units / unit to nodes;
- edge to units / unit to edges;
- claim to evidence units / unit to claims.

It is rebuildable solely from canonical graph references, merge lineage, and the provenance ledger.

### 10. StageView is an explainable projection

A `StageViewProjector` accepts graph build output plus stage, task intent, upstream settlement state, gap state, and token budget. It returns selected nodes, edges, source units, upstream conclusions, unresolved conflicts, missing capabilities, coverage summary, token estimate, and selection reasons.

Stages migrate incrementally. During migration, `SemanticAtlas` may locate candidate units when graph coverage is insufficient, but its results must be converted into anchored selections and labeled as fallback.

### 11. Versioned invalidation chain

Artifacts use explicit schema versions and content digests:

```text
snapshot
  -> anchored text units
  -> linguistic and semantic extractions
  -> ledger / merge decisions / graph / source index
  -> stage views
  -> stage artifacts
```

A changed upstream digest invalidates only downstream projections.

## Risks / Trade-offs

- [Xberg does not expose structure uniformly for every format] → Preserve capability gaps and unsupported coverage instead of fabricating structure.
- [The first canonicalizer will be conservative] → Prefer `defer` and conflicts over false merges; add optional scorers later.
- [The ledger can become an oversized event-sourcing system] → Limit v1 events to source, extraction, grounding, canonicalization, conflict, and projection lineage.
- [Stage migration can break existing runnable flows] → Keep the current SemanticAtlas path as a labeled fallback until all six stages consume StageView.
- [Multiple adapters can introduce accidental vendor semantics] → Normalize every adapter into stable backend descriptors and GraphExtraction candidates.
- [Dirty worktree contains unrelated Agent integration changes] → Restrict this change to new foundation modules and narrow application/stage integration edits.

## Migration Plan

1. Introduce new foundation models and preserve the existing runtime path.
2. Replace the spike builder with the deep `ArticleGraphBuilder` and persist complete build artifacts.
3. Add StageView projection and migrate Stage 1 first with a SemanticAtlas fallback.
4. Migrate Stages 2-6 once the first graph-to-source-to-stage loop is verified.
5. Remove the spike artifact reader and retire direct retrieval-packet construction where no longer needed.

Rollback consists of disabling StageView consumption and using the existing SemanticAtlas path; immutable source snapshots and raw extraction artifacts remain valid.

## Open Questions

No blocking design questions remain. Concrete HanLP/DeepKE adapter selection, model licenses, and CompletionPlan semantics are intentionally deferred to later changes.
