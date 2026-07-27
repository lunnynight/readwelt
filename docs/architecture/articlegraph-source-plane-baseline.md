# ArticleGraph Source Plane Architecture

Recorded: 2026-07-27
Change: `harden-article-graph-source-plane`

## Product boundary

ArticleGraph is deterministic preprocessing and navigation for AI. It reduces
re-reading, token use, latency, and uncertainty by keeping the article
addressable and by exposing grounded locating signals. It does not replace the
AI that performs Readwelt's six-stage reading process.

The implemented boundary is:

```text
original source bytes / source_document root
                      |
                      v
normalized text artifact + Source Plane
  - AnchoredTextUnit
  - complete unit/gap ranges
  - preserved source elements and structure
  - independent capability and coverage records
                      |
                      v
advisory ArticleGraph locating signals
  - mentions, nodes, edges, claims
  - ambiguity, conflicts, confidence, provenance
                      |
                      v
SourceIndex + append-only ProvenanceLedger
  - source-first traversal
  - knowledge <-> source lookup
  - typed provider-material closure
                      |
                      v
bounded and paged StageView provider envelope
  - hard serialized-input budget
  - omissions, blocking records, coverage, continuation
                      |
                      v
six-stage AI conclusions
  - may cite source and graph identities
  - cannot be written back as source facts
```

`CompletionPlan`, external research orchestration, gap-completion scheduling,
and the Completion Engine are deliberately outside this change. The stable
preprocessing and provider-input boundary is being completed first.

## 1. Original source artifact and source root

File-backed ingestion stores the original bytes as a content-addressed
artifact. The snapshot contains an addressable `source_document` element whose
`raw_payload_ref` points to those bytes. Top-level parser elements become its
children. Document and snapshot identity remain bound to the original-source
digest, so two extraction-empty PDFs do not collapse into one empty-text
identity.

Implementation:

- [`runner/snapshot.py`](../../src/readwelt/runner/snapshot.py) creates the raw
  artifact and source-root element.
- [`domain/documents.py`](../../src/readwelt/domain/documents.py) defines the
  persisted source element and snapshot contracts.
- [`test_raw_source_plane.py`](../../tests/runner/test_raw_source_plane.py)
  verifies distinct extraction-empty identities and source-root traversal.

For an image-only or scanned PDF, this guarantees that the original file
remains retrievable and auditable. It does **not** claim that OCR text, layout,
or page geometry exists. Empty normalized text and missing OCR/layout remain
explicit capability gaps.

## 2. Normalized Source Plane

The normalized text artifact is projected into stable
`AnchoredTextUnit` records plus ordered `SourceRangeRecord` records. Unit ranges
and explicit gap ranges together cover normalized text without turning
separators into semantic graph nodes. Backend-exposed text and non-text objects
remain `SourceElement` records even when their semantic or geometric projection
is unavailable.

The Source Plane is authoritative for source reachability. Its implementation
lives in:

- [`article_ir/models.py`](../../src/readwelt/article_ir/models.py) for units,
  ranges, coverage records, and the Source Plane manifest;
- [`article_ir/unitizer.py`](../../src/readwelt/article_ir/unitizer.py) for
  deterministic unit/range construction and exact reconstruction;
- [`runner/xberg.py`](../../src/readwelt/runner/xberg.py) for Xberg projection
  and fail-empty structural diagnostics.

Native identity, raw payload handle, order, parent/child, previous/next,
heading, page, table, figure, and caption information are preserved only when
the backend exposes them or a deterministic projection resolves them.
Ambiguous relationships are recorded, not guessed.

## 3. Advisory ArticleGraph locating signals

[`article_graph/builder.py`](../../src/readwelt/article_graph/builder.py)
constructs immutable extraction artifacts, canonical objects, merge decisions,
conflicts, and the ledger/index projections. Semantic nodes, edges, and claims
are source-grounded machine candidates. Their role is to help the AI locate
potentially relevant passages and relationships.

ArticleGraph cannot declare the final main problem, argument structure, hidden
premise, author model, validity boundary, or transferable principle. Those are
six-stage outputs. Semantic extraction failure removes locating hints but does
not remove Source Plane ranges, elements, or source-first traversal.

## 4. SourceIndex and provenance closure

[`provenance/source_index.py`](../../src/readwelt/provenance/source_index.py)
retains knowledge-to-unit and unit-to-knowledge projections and adds
source-first lookup by range, ordinal, section, heading, element, page,
neighbors, and lexical locator.

[`provenance/closure.py`](../../src/readwelt/provenance/closure.py) validates
the material actually serialized for a provider. A provider-visible text
unit/slice or graph node/edge must resolve through the matching SourceIndex,
canonicalization and unitization ledger events, and typed Source Plane records.
Unknown, mismatched, or stale references return diagnostics and no fabricated
source association.

## 5. Bounded StageView provider envelope

StageView is a resumable provider-input projection, not a one-shot summary:

- [`stage_views/projector.py`](../../src/readwelt/stage_views/projector.py)
  assembles the stage-specific source and advisory graph slice;
- [`stage_views/selection.py`](../../src/readwelt/stage_views/selection.py) and
  [`stage_views/paging.py`](../../src/readwelt/stage_views/paging.py) implement
  source-first rescue and deterministic paging;
- [`stage_views/cursors.py`](../../src/readwelt/stage_views/cursors.py) binds
  continuation to the source revision, policy, schema, and index digest;
- [`stage_views/serialization.py`](../../src/readwelt/stage_views/serialization.py)
  enforces the hard budget against the complete provider-bound envelope and
  pages large omission/conflict/capability diagnostics.

Oversized units are deterministically sliced with their parent source identity
or returned as explicit blocking records. A document larger than the provider
budget is traversed with continuation; it is not silently truncated and does
not require normal full-document prompt injection.

## 6. Six-stage AI conclusion boundary

The provider receives source excerpts, typed provider-visible material,
advisory graph objects, upstream conclusions, uncertainty, coverage, and
continuation state. It returns stage candidates under the fixed six-stage
contract.

[`stages/ai_boundary.py`](../../src/readwelt/stages/ai_boundary.py) prevents a
provider from declaring its output to be a source fact or ArticleGraph object.
A stage conclusion may cite admitted source anchors and graph identities, but
it remains a stage conclusion. Readwelt owns stage order, input policy,
settlement, persistence, and completion state; the Agent host only reasons
inside that contract.

## Coverage dimensions are not interchangeable

| Dimension | What it proves | What it does not prove |
|---|---|---|
| Original-source preservation | Original bytes and source-root identity remain addressable | OCR text or layout was recovered |
| Normalized-range coverage | Every normalized character resolves to a unit or explicit range | Parser structure or semantics are available |
| Element coverage | Every backend-exposed element is preserved | The element was semantically interpreted |
| Structural capability | Available order, hierarchy, page, geometry, and relations were projected | Missing structure was reconstructed |
| Semantic capability | A backend produced grounded locating candidates | The six-stage interpretation is correct |
| Traversal visited | A source identity was considered during paging | It was selected or shown to the provider |
| Selected/serialized/presented | Material entered successive provider-envelope surfaces | The model cited or used it |
| Cited/critical | Output citations and required anchors are accounted for | Whole-document source coverage is complete |

The compatibility `coverage_complete` field is conservative. It cannot replace
the persisted Source Plane manifest or the StageView coverage envelope.

## Measured backend decisions

The [Xberg capability report](../../reports/xberg-capability-probe-2026-07-27.json)
for pinned Xberg `1.0.0rc38` extracted content from TXT, HTML, EPUB, and a native
PDF, but exposed zero measured nodes, elements, pages, offsets, relationships,
or reading-order fields in those probes. The image-only PDF control produced
zero normalized characters. Xberg therefore remains primary ingestion, but it
is currently content-first rather than a sufficient structure/OCR backend.

The complete `docling==2.114.0` package is now an optional production
structure/layout/OCR fallback behind the stable Source Plane adapter;
`docling-core` remains its data model, not the PDF parser. The fallback runs
only for PDFs where Xberg has no structure or empty content. It requires
pre-downloaded local model artifacts, disables remote services and external
plugins, preserves the original PDF source root, and records its own findings.
The [real fixture probe](../../reports/docling-structural-fallback-probe-2026-07-27.json)
uses 633,340,087 bytes of explicitly downloaded local layout, TableFormer, and
RapidOCR artifacts. It converted the 50-page native PDF successfully into
143,851 characters, 865 structure records, and 841 page/geometry-bearing
records. The one-page scanned fixture has no native PDF text layer; RapidOCR
recovered 1,619 characters, 40 structure records, and 33 page/geometry-bearing
records. Complete traversal includes groups, picture descendants, and all
Docling content layers while retaining each element's `content_layer`
provenance. Both fixtures have zero unresolved parent, child, or
structural-relation references. Runtime network services and external plugins
remained disabled.

The [linguistic bake-off report](../../reports/linguistic-backend-bakeoff-2026-07-27.json)
shows that Stanza executed successfully on three Chinese units with exact
offset recovery in that focused fixture. This approves only an optional
benchmark adapter. It is not a default backend and does not establish
representative long-document quality, production memory, or cold-start cost.
The default remains deterministic source-first operation.

The full source, license, and adoption decisions are recorded in
[ArticleGraph Open-source Adoption Record](articlegraph-open-source-adoption.md).

## Acceptance state

The representative corpus manifest now includes TXT, HTML, native PDF,
image-only scanned PDF, and EPUB cases, including documents over 100,000
Chinese characters. See
[`corpus_manifest.json`](../../benchmarks/articlegraph/corpus_manifest.json).

The following list is the early implementation snapshot recorded before the
final acceptance run; it is retained as historical context rather than current
project status:

- corpus assembly is complete;
- complete bounded traversal across every corpus document is not yet accepted;
- the required Recall@budget, critical-miss, latency, memory, fallback, and
  unresolved-projection report is not yet complete;
- lexical/dense/hybrid/reranking/source-rescue comparison under identical
  budgets is not yet complete.

Those acceptance gaps were subsequently closed by the
[final long-document report](../../reports/articlegraph-long-document-acceptance-2026-07-27.json)
and reconciled in the
[six-gap implementation audit](../audits/articlegraph-six-gap-test-audit-2026-07-27.md).
The final report records 7/7 passing cases, complete unit/range/element/source-root
reachability, complete bounded traversal, closed structural references, and
hard-budget compliance under its declared conservative counter. Its content
digest is
`sha256:25b905202e73d70f5d8ef52fa2a53f60b052ab9a0d1d3472591ca30e930a7622`.

This proves complete Source Plane reachability and bounded locating traversal;
it does not prove exhaustive semantic ArticleGraph extraction or six-stage
understanding quality. No fixed token-saving percentage should be inferred
beyond the measurements in the report.

## Historical baseline

Before this hardening change, SourceIndex was mainly knowledge-to-unit,
StageView was one-shot, separators lacked independent range identities, and
provider-bound serialized input was not the authoritative hard-budget surface.

An early narrative observation recorded degraded coupling with zero cycles and
zero god files, but it did not preserve a machine-readable scan and is not used
as the comparison authority. The retained `sentrux-lite` checkpoint is preserved
byte-for-byte in
[`reports/sentrux/sentrux-lite-prechange-2026-07-27.json`](../../reports/sentrux/sentrux-lite-prechange-2026-07-27.json)
with SHA-256
`aa795e28c31fd672c27fc2ebdb732618c2bbc7a398a2721287291672e7214031`.
It records quality `9206`, coupling `64.21`, zero cycles, and two god files.
Because its timestamp falls within the hardening work, it proves structural
non-regression from that recorded checkpoint rather than claiming a clean
before-state for every earlier edit in the change.

The final direct gate records quality `9417`, coupling `64.17`, zero cycles,
and zero god files. Code Intel's independent `sentrux-native` v2 lane records
quality `9416`, coupling `64.17`, zero cycles, and zero god files. The two-engine
onboarding and preservation policy are recorded in
[`reports/sentrux/articlegraph-baseline-engine-onboarding-2026-07-27.json`](../../reports/sentrux/articlegraph-baseline-engine-onboarding-2026-07-27.json).
The six ArticleGraph and Source Plane scopes pass the current zero-cycle,
maximum-complexity, and no-god-file constraints in
[`reports/sentrux/articlegraph-scoped-gates-2026-07-27.json`](../../reports/sentrux/articlegraph-scoped-gates-2026-07-27.json).
No historical per-directory baseline survived, so that artifact does not claim
a scoped delta; change-level non-regression is established by the retained root
checkpoint.
Neither comparison is presented as evidence that unrelated repository debt was
fixed by this change.
