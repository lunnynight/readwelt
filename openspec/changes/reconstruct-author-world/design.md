## Context

See `proposal.md` for the motivation and user-facing scope. The current pipeline already freezes stages 1–2 before stages 3–6, and `ReadingClaim` carries stage, source anchors, upstream claim ids, limitations, decisions, and typed source citations. Stage 3 admits external evidence through `StageView`; stage 4 records competing interpretations through provenance. The Markdown projection currently renders stage claims as independent bullets, so it does not make the formation path from world conditions to article question and article choices explicit.

## Goals / Non-Goals

**Goals:**

- Add a durable, provider-neutral representation for author-world items and the relations connecting them to article claims.
- Preserve source closure: every published item and relation is traceable to article anchors, upstream claims, admitted external evidence, or an explicit unresolved gap.
- Make evidence class and epistemic status visible to the reader without allowing external context to rewrite stages 1–2.
- Compile a readable causal chain while retaining the existing settled-claim and withholding rules.

**Non-Goals:**

- Build a general biography database or infer the author's private psychology.
- Change retrieval, source-plane preservation, stage order, or the stage-1/stage-2 article-only boundary.
- Create a reader profile or personalize the canonical reading bundle.
- Treat ArticleGraph locating candidates as author-world conclusions.

## Decisions

### 1. Add a typed author-world relation layer rather than encode the chain in claim prose

Introduce a small immutable domain contract for world items and directed relations. A world item represents a bounded condition, concept, problem pressure, or article choice; a relation records `from`, `to`, relation kind, decision, limitations, and typed citations. The aggregate is attached to the settled reading bundle or its projection with a schema version and content digest.

This avoids relying on sentence wording or report heading order to recover causality. Reusing only `ReadingClaim.source_claim_ids` would lose the distinction between a world condition and the article claim it explains. A graph database is unnecessary for the bounded per-document chain and would add persistence and migration cost.

### 2. Keep evidence classes explicit at the domain boundary

Each world item and relation MUST carry an evidence class with at least `article_explicit`, `external_context`, `interpretation`, and `unresolved`. Article-explicit entries cite source anchors or article claims; external-context entries cite admitted external evidence; interpretations cite their premises and preserve an interpretation identity. Validation rejects a published entry whose citations do not match its evidence class.

This makes provenance inspectable and prevents a provider from turning a plausible background story into an unqualified fact. The alternative—one free-form provenance map—is smaller initially but cannot enforce the boundary or support reliable report labels.

### 3. Generate author-world material in stage 3/4, then settle it with existing ledger rules

Stage 3 should produce conditions and prerequisite concepts that the article compresses; stage 4 should connect those conditions to problem genesis, author selection, and competing explanations. The provider response schema should accept typed world items/relations alongside ordinary claims. Runtime validation should apply existing anchor/source-claim checks, decision settlement, and withholding behavior rather than inventing a second acceptance system.

The article-only restriction remains unchanged: stages 1–2 cannot receive external evidence. Stage 3/4 may use only external material admitted by the `StageView`; any omitted evidence remains visible as an omission or gap.

### 4. Render a causal chain first, details second

Extend the Markdown compiler with an "作者世界如何生成文章" section. Render only ledger-eligible items and relations, ordered from world condition to problem pressure to article choice. For each link, show a compact evidence-class label, limitations, and traceable claim/anchor identifiers. Render unresolved links in the existing gaps/undetermined area and retain the detailed "文章背后的世界" and "作者的思想模型" sections for compatibility.

A dedicated chain section is preferable to silently changing existing headings: it gives readers the missing causal orientation while preserving consumers that rely on the current nine-section report.

### 5. Version the new contract and provide a deterministic compatibility path

Use a new schema version for bundles containing author-world data. Historical bundles without the field continue to render with an explicit "作者世界尚未重建" message and their existing sections. No migration should fabricate world relations from old prose claims. Serialization, JSON projection, and Markdown output must remain deterministic.

## Risks / Trade-offs

- [Risk] Model-generated causal links may sound more certain than their evidence supports → Require typed evidence classes, source closure, decision settlement, and visible limitations; reject invalid citation combinations.
- [Risk] A chain can imply historical causation where the source only supports correlation → Use relation kinds that distinguish context, enables, motivates, and interprets; require unresolved/qualified status when causality is not established.
- [Risk] New fields increase provider request size → Include bounded world items and relations in the same stage view budget and apply the existing hard serialized-token settlement.
- [Risk] Existing bundles lack the new aggregate → Treat the field as optional for historical decoding and render a deterministic unavailable state; never synthesize data.
- [Risk] A second graph may duplicate ArticleGraph locating data → Keep ArticleGraph as machine-locating input only; author-world objects are settled reading conclusions with independent evidence and ledger status.

## Migration Plan

1. Add the versioned domain and serialization contracts with historical-bundle compatibility.
2. Extend stage request/response validation and settlement for stage-3/4 author-world material.
3. Persist the settled aggregate in the canonical bundle and expose it through JSON projections.
4. Add the causal-chain Markdown section and regression coverage for complete, competing, incomplete, and historical cases.
5. Run the full affected test modules and a provider-free agent scenario; if the feature is rolled back, omit the optional aggregate and retain the existing report sections.

## Open Questions

- The first implementation can use the existing stage-3/4 external evidence admission model; the exact set of relation-kind labels can be finalized while implementing the typed contract without changing the observable requirements above.
