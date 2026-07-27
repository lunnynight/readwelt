## Context

Readwelt currently has deterministic text unitization, anchored units, immutable extraction artifacts, a canonical graph, an append-only provenance ledger, a knowledge-to-unit `SourceIndex`, and token-estimated StageViews. These are useful foundations and MUST be preserved.

The current implementation still has four product-level gaps:

1. Xberg structure is projected by matching unique exact paragraph text. Repeated or partial elements lose structure; nodes and elements are treated as alternatives; parent/child trees, explicit reading order, complete pages, and table/figure/caption identity are not preserved reliably.
2. Unit coverage excludes whitespace separators. The normalized source artifact retains the full text, but there is no explicit range record for every gap, so “complete coverage” is currently stronger than the evidence.
3. `SourceIndex` primarily maps canonical knowledge objects to text units. It does not provide source-first range, ordinal, structural, page, or element navigation independent of semantic extraction.
4. StageView is a one-shot selection. Over-budget units can be silently omitted, there is no continuation cursor or rescue traversal, and build/index coverage can be reported as view completeness.

ArticleGraph is a deterministic preprocessing and locating substrate. It must reduce AI input cost and uncertainty while preserving the AI’s responsibility for recovering the article’s main line, argument structure, hidden premises, author model, boundaries, and transferable principles.

The repository contains dirty worktree changes in ArticleGraph, StageView, provider, application, and tests. They are treated as existing user work. Implementation MUST integrate with them and MUST NOT reset or overwrite unrelated changes.

## Goals / Non-Goals

**Goals:**

- Preserve and address the complete normalized source and every exposed non-text source element.
- Navigate any long document through deterministic, bounded, resumable traversal without normal full-text injection.
- Preserve available native structure without fabricating unavailable structure.
- Separate source completeness, semantic capability, retrieval selection, presentation, and citation coverage.
- Keep semantic objects as provenance-bearing locating candidates rather than stage conclusions.
- Reuse mature open-source interfaces and algorithms through narrow adapters whenever they satisfy the contract.
- Validate the design on real PDF/EPUB/HTML/TXT inputs and 100,000+ character documents.

**Non-Goals:**

- Generating final Stage 1–6 understanding inside ArticleGraph.
- Implementing `CompletionPlan`, external research, or completion scheduling in this change.
- Writing Stage 3–6 conclusions back into source facts or extraction candidates.
- Replacing Xberg without a measured format capability failure.
- Importing an entire GraphRAG, KAG, Docling Graph, DeepKE, Splink, or OpenLineage product stack when a narrow adapter or algorithm is sufficient.
- Treating embeddings, graph node count, or a single model packet as evidence of completeness.
- Guaranteeing a fixed token-reduction percentage before corpus measurement.

## Decisions

### 1. Split Source Plane from Semantic Graph

`ArticleSourcePlane` will be the authoritative preprocessing substrate for a document revision. It will contain:

- the immutable normalized text artifact;
- the immutable original source artifact and an addressable source-root element for binary/container inputs, including inputs whose normalized extraction is empty;
- ordered addressable text ranges, including explicit separator/gap ranges where text units do not own the bytes;
- source elements with stable IDs, native/backend references, kinds, raw payload handles, page/geometry when available, and projection status;
- structural references such as parent, children, previous, next, heading trail, and reading order;
- a source coverage manifest and capability gaps.

`ArticleGraph` will reference Source Plane identities. Entity, relation, claim, evidence, example, objection, and qualification objects remain immutable extraction/canonicalization candidates with epistemic status and provenance.

Alternative considered: extend canonical graph nodes to represent all document structure. Rejected because it duplicates the document tree, mixes source facts with inferred knowledge, and makes semantic extraction failure threaten source reachability.

### 2. Preserve Exact Source Reachability Without Turning Separators into Knowledge Nodes

Meaningful `AnchoredTextUnit` objects remain the chunking unit. Any normalized range not owned by a text unit will be represented by an explicit source range/gap record referencing the normalized artifact. This permits exact reconstruction and offset lookup without creating semantic graph nodes for whitespace.

Every non-empty normalized range MUST resolve to a unit or range record. Every non-text element exposed by a backend MUST resolve to a source element record even if its content cannot be semantically interpreted.

Document and snapshot identity for ingested files MUST include the original source digest rather than only the normalized-text digest. This prevents two different image-only or extraction-empty files from collapsing to the same identity.

Alternative considered: retain non-whitespace-only coverage and call the normalized artifact the fallback. Rejected because it cannot prove exact range navigation and hides the difference between preserved bytes and indexed ranges.

### 3. Use Xberg First, Then Measured Structural Fallbacks

Xberg remains the primary parser. A format capability probe will record what Xberg actually exposes for TXT, HTML, EPUB, native PDF, scanned PDF, tables, images, captions, pages, geometry, references, and reading order.

The adapter will consume nodes and elements cumulatively, prefer native IDs/offsets/relationships over exact-text matching, and record ambiguity instead of guessing. Exact-text alignment is a last-resort projection method and must support occurrences rather than uniqueness-only matching.

Docling Core will be evaluated as an optional structural fallback or secondary projection source for formats where Xberg lacks required structure. We will adapt its reference, page/bbox/charspan, hierarchical chunk, and iteration patterns; we will not convert the whole Readwelt model into `DoclingDocument`.

### 4. Layer SourceIndex Instead of Replacing It

The existing knowledge↔unit projections are retained. Source-first projections are added:

- normalized offset/range ↔ unit or gap record;
- section/heading/element/page ↔ ordered units;
- ordinal ↔ unit;
- parent/children/previous/next navigation;
- lexical locator result ↔ source range;
- knowledge object ↔ source unit/range.

All projections are rebuildable and deterministic. Unknown references fail empty with an explicit diagnostic; they do not fabricate a source association.

GraphRAG’s TextUnit reverse-map pattern and KAG’s explicit source-chunk relationship inform these projections, but their runtimes are not dependencies.

### 5. Make StageView a Resumable Traversal

StageView projection becomes:

1. select orientation and must-hit anchors;
2. resolve source identities;
3. add structural/lexical/semantic candidates;
4. expand neighborhood under policy;
5. serialize the complete provider-bound packet;
6. enforce the hard serialized-input token budget;
7. return a coverage manifest and continuation cursor.

The budget is settled twice: first while projecting the StageView, then again
after the stage engine adds anchors, retrieval hits, upstream claims, external
evidence, request metadata, and provenance. The second settlement is
authoritative because it measures the exact final `StageRequest` serialization.

Both settlements use an auditable token-counter contract. A counter records its
stable identity and whether it is provider-exact or a conservative upper bound.
The safe built-in fallback counts one token per UTF-8 byte only for provider
profiles that explicitly declare at most one input token per byte; it is never
reported as an exact tokenizer. Unknown provider/tokenizer profiles fail closed
unless the host supplies an exact counter. The final settlement measures the
actual provider envelope, including static instructions, serialized user
content, response schema, and transport wrapping. Resolver compare/fallback
planning reserves the maximum measured envelope across every possible provider,
and every provider repeats the measurement immediately before invocation.

The cursor records document revision, policy/schema versions, traversal frontier, visited identities, and deterministic ordering state. It is content-addressed or integrity-protected so it cannot silently resume against another revision.

The rescue ladder is:

1. initial bounded packet;
2. previous/next and parent/child expansion;
3. targeted second retrieval;
4. section-complete paged traversal;
5. full text only for documents that fit the declared hard budget.

An over-budget single unit MUST be deterministically split with derived provenance or produce an explicit blocking record. Silent omission is forbidden.

The traversal frontier is a Source Plane frontier, not only a text-unit list.
Range/gap records may be represented by compact reachability accounting rather
than prompt text. Non-text source elements, including tables, figures, captions,
and the original source-root artifact, must be selected/paged or explicitly
blocked and remain recoverable through the continuation state.

Alternative considered: return the highest-scoring one-shot packet and rely on the model to ask again. Rejected because it cannot prove completeness, does not expose omissions, and fails on 100,000-character documents.

### 6. Separate Coverage Dimensions

`CoverageManifest` will report at least:

- source indexed coverage;
- structural capability coverage;
- semantic extraction capability coverage;
- traversal visited coverage;
- selected coverage;
- presented-to-provider coverage;
- cited coverage;
- critical-anchor coverage;
- omitted identities and reasons.

No single `coverage_complete` boolean may collapse these dimensions. Compatibility fields may remain temporarily but must be derived conservatively and deprecated.

### 7. Enforce the AI Boundary

ArticleGraph and Source Plane may state:

- source facts;
- parser/linguistic observations;
- machine extraction candidates;
- canonicalization decisions;
- confidence, ambiguity, conflict, and provenance;
- locating and traversal hints.

They MUST NOT state that the article’s main problem, argument, author model, validity boundary, or transferable principle is final. Those are six-stage outputs. Stage outputs may reference graph/source identities but may not be reclassified as source facts.

### 8. Require an Open-Source Adoption Record

Before adding bespoke parser, chunker, provenance, retrieval, entity-resolution, or Chinese linguistic logic, the task must record:

- candidate repository and exact revision;
- code and model/data licenses;
- required capability and measured result;
- integration weight and transitive dependencies;
- adopted interface/algorithm;
- rejected product-layer behavior;
- reason a thin adapter is insufficient, if building in-house.

Initial decisions:

- Xberg: keep as primary input backend; measure per-format structure.
- Docling Core/Graph: adapt reference, provenance, fail-empty merge, and hierarchical patterns; evaluate Core as optional structural fallback.
- GraphRAG/KAG: adapt bidirectional source-map and bounded-context patterns, not the full runtime.
- HanLP/PaddleNLP/Stanza: first Chinese backend bake-off.
- LTP: authorization-limited control.
- DeepKE: schema/output reference only, not the default runtime.
- Splink: optional later mention-pair scorer only.
- PROV: optional export interoperability.
- OpenLineage: envelope/facet inspiration only.

## Risks / Trade-offs

- [Multiple parser representations diverge] → Keep one Readwelt Source Plane contract, retain backend-native references, and compare projections through capability probes rather than merging opaque object models.
- [Exact range coverage increases artifact size] → Store ranges and content hashes, not duplicated text; page and stream large artifacts; measure deduplication only after correctness.
- [Continuation cursors become stale] → Bind cursors to document revision, Source Plane schema, policy, and index digests.
- [Hard budgets split coherent evidence] → Prefer structural boundaries, preserve derived provenance, expose split/omission reasons, and use rescue traversal.
- [Open-source dependency weight exceeds benefit] → Prefer narrow adapters and copied algorithms only when their licenses permit; record exact decisions.
- [Model licenses differ from code licenses] → Treat code, model, and dataset licenses as separate adoption gates.
- [Current root Sentrux gate is already below baseline] → Use scoped ArticleGraph/Source Plane sessions, avoid adding cross-module dependencies, and compare the final root gate without claiming unrelated degradation as fixed.
- [Existing dirty StageView/application changes overlap] → Inspect and preserve the current diff before each edit; integrate incrementally with focused tests.

## Migration Plan

1. Add red tests for repeated text, partial elements, nodes+elements, exact gap/range reachability, deterministic structure traversal, and StageView continuation.
2. Introduce versioned Source Plane records alongside existing anchored units and normalized artifacts.
3. Extend Xberg projection and SourceIndex without removing existing knowledge mappings.
4. Add versioned StageView coverage/cursor fields while retaining conservative compatibility readers.
5. Migrate stage consumers to resumable traversal and hard provider-bound budget checks.
6. Run format capability probes and adopt optional backend adapters only after the adoption gate.
7. Run real long-document acceptance, OpenSpec strict validation, focused regression tests, and scoped/root Sentrux gates.

Rollback is artifact-version based: old readers continue to consume the prior schema while new Source Plane, index, and StageView artifacts are built under new schema versions. No migration rewrites historical immutable artifacts.

The complete aggregate Source Plane therefore receives a schema version
distinct from historical `anchored-text-unitization.v1`; adding optional fields
while retaining the same aggregate version is not sufficient rollback evidence.
Compatibility readers must decode and validate real historical payloads, not
only accept their top-level JSON shape.

## Open Questions

- Which Xberg formats expose stable native element IDs and offsets in the pinned production version?
- Does Docling Core provide enough incremental value on native/scanned PDFs to justify an optional installed extra?
- Which HanLP/PaddleNLP/Stanza model set satisfies both offset recovery and the intended distribution license?
- What provider-specific tokenizer is authoritative for the first hard serialized-input budget gate?
