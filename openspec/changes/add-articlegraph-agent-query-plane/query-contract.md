# ArticleGraph Agent Query Contract

## Authority and Versioning

This document defines the public semantics shared by the CLI, Python query
service, and six-stage reader. The normative wire models live in
`readwelt.article_graph.query_models`; each independently persisted or exchanged
object carries its own `readwelt.articlegraph-*.v1` schema version.

Within v1, readers accept omitted optional fields and apply documented defaults.
They reject unknown fields and unknown schema versions. A cross-version migration
must be explicit; consumers never guess that an old StageView cursor, collection
page cursor, query continuation, or receipt has current semantics.

## Common Execution Semantics

Every operation executes against one immutable ArticleGraph snapshot and its
matching `SourceIndex`.

1. Normalize the request into a stable document ID, operation, query/object seeds,
   filter, budget, consumer stage, and task intent. Compute the normalized request
   digest before retrieval.
2. Admit deterministic exact-ID and lexical candidates first. Optional semantic
   backends may add or rerank candidates, but cannot replace source provenance or
   make the operation unavailable.
3. Apply filters before graph expansion. A filter narrows results; it never grants
   access beyond the operation or budget.
4. Order results by operation-specific relevance, source order, object kind, and
   stable ID. Every tie is resolved deterministically.
5. Enforce hit, visited-object, traversal-depth, relation-path, evidence-character,
   source-byte, and estimated-token limits inside the service. A reached limit
   returns a partial page with an explicit truncation reason and, when resumable,
   an opaque snapshot-bound continuation.
6. Return a `QueryPage` whose `QueryHit` evidence resolves to real Source Plane
   identities. Unavailable page, bounding-box, or character coordinates remain
   null. A dangling source reference produces `dangling_source_reference`; it is
   never downgraded to an ungrounded hit.
7. Persist a `QueryReceipt` for every successful call, including empty results. The
   page and receipt agree on snapshot, operation, normalized digest, ordered IDs,
   budget, usage, continuation digests, backend, and result digest.

Empty-but-valid results are successful pages with no hits. Invalid input, invalid
continuations, missing snapshots, dangling evidence, and internal failures use the
typed error envelope and never masquerade as empty success.

## Public Operations

| Operation | Required input | Semantics | Ordering | Continuation |
|---|---|---|---|---|
| `search` | Non-empty query, object IDs, or a narrowing filter | Retrieve deterministic exact-ID and lexical candidates across source units/elements, mentions, nodes, edges, and claims. Optional semantic candidates are additive. | Exact ID, exact text/label, lexical score, source order, kind, stable ID | Offset plus ordering key; snapshot/query/filter/budget bound |
| `locate` | Query text, source/page/offset filter, or object IDs | Resolve the requested text or graph object to the most precise truthful source locators. It may return document/unit precision when finer Xberg coordinates are unavailable. | Locator precision, source order, stable ID | Ordered locator offset; snapshot/query bound |
| `evidence` | One or more graph/source object IDs | Resolve claims, relations, nodes, or source identities to exact evidence envelopes. Every returned envelope includes graph ownership, source locator, and provenance digest. Any referenced-but-missing source identity fails closed. | Input seed order, source order, stable ID | Ordered evidence offset; snapshot/query bound |
| `neighbors` | One or more graph/source object IDs | Traverse admitted relation or source-neighborhood edges up to `max_depth`, returning the relation path for every expanded result. | Hop count, relation kind, source order, stable ID | Remaining frontier, visited IDs, ordering key; snapshot/query bound |
| `trace_claim` | One or more claim IDs | Return the claim, supporting/opposing graph path, and evidence units/elements needed to audit how it was assembled. Missing evidence is an error, not a partially grounded claim. | Input claim order, path length, relation kind, source order, stable ID | Remaining claim/path frontier; snapshot/query bound |
| `expand_context` | Seed IDs or query plus a stage/task intent | Build a bounded, source-ordered context expansion for a reading stage. This is the compatibility destination for eager StageView projection, not a license to return the whole document. | Seed relevance, source adjacency, graph distance, source order, stable ID | Remaining source/graph frontier and visited IDs; snapshot/query bound |

Presenting a continuation with a different snapshot, operation, normalized query,
filter, or budget returns `restart_required` or `invalid_continuation`. The service
does not continue against rebuilt content and does not reuse the old offset-only
ArticleGraph collection cursor.

## Result and Error Semantics

- `QueryHit.match_reason` records why the object entered the page; it is not a
  confidence score.
- `score` is backend-relative and nullable. Stable ordering never depends on an
  unavailable score.
- `epistemic_status`, confidence lineage summary, ambiguity, source IDs, relation
  path, and evidence are copied from canonical artifacts; the query layer does not
  upgrade uncertainty.
- `QueryUsage` is measured, not requested: it reports returned/visited objects,
  traversed edges, paths, evidence characters, source bytes, and estimated tokens.
- `budget_exhausted` is reserved for requests that cannot produce even a valid
  bounded page. Normal resumable truncation is a successful page with a reason.
- `restart_required` is the only error code that sets `restart_required=true`.
  CLI adapters map typed codes to stable exit codes; Python callers receive the
  same typed envelope from the service boundary.

## StageView Compatibility Mapping

`StageView` remains a rollback and migration adapter. It is not the public query
response, and its cursor cannot be passed as a query continuation.

| Existing StageView field | Query-plane destination | Mapping rule |
|---|---|---|
| `schema_version` | Adapter metadata only | Preserve in compatibility artifacts; never relabel it as a query schema version. |
| `snapshot_id` | `QueryPage`, `QueryReceipt`, `QueryContinuation` | Copy exactly and require it to match the graph/source snapshot. |
| `stage`, `task_intent` | `ArticleGraphQueryRequest.consumer_stage`, `.task_intent`; receipt stage | Preserve as request/receipt intent metadata; do not use it to change core operation semantics. |
| `nodes` | `QueryHit(kind=node)` | Map ID, kind, label/text, epistemic status, confidence/method, ambiguity, source IDs; projection selection becomes `match_reason`. |
| `edges` | `QueryHit(kind=edge)` plus `RelationHop` | Map edge and endpoint IDs, relation kind, uncertainty, source IDs; explicit traversal puts the edge into the relation path. |
| `claim_candidates` | `QueryHit(kind=claim)` | Map claim text/status/confidence and resolve evidence unit/element IDs into fail-closed `EvidenceEnvelope` locators. |
| `text_units` | `QueryHit(kind=source_unit)` and `EvidenceEnvelope` | Map unit ID, selected or sliced text, ordinal/source order, anchors, and exact source locators. A text slice must retain its original unit/range identity. |
| `source_ranges` | `SourceLocator(precision=exact_range)` | Map range ID and offsets. Content hash remains provenance metadata; do not infer page/bounding box. |
| `source_elements` | `QueryHit(kind=source_element)` and `SourceLocator` | Map element/page/bounding box/structural identity exactly; missing coordinates remain null. |
| `upstream_claims` | `trace_claim` or `expand_context` seeds | Preserve claim IDs and citations; do not emit an unverified upstream claim as new source evidence. |
| `selection_reasons` | `QueryHit.match_reason` | Preserve the reason for admitted objects; multiple reasons use the deterministic primary reason with remaining reasons in adapter metadata. |
| `token_budget`, `hard_serialized_token_budget` | `QueryBudget.max_estimated_tokens` | Use the stricter positive limit. StageView's selected-text scope is recorded when it differs from the complete query-envelope scope. |
| `estimated_tokens` | `QueryUsage.estimated_tokens` | Recount the complete query envelope with the query-plane counter; do not copy a differently scoped estimate as measured usage. |
| `coverage_complete`, `coverage` | Receipt/usage plus evaluation coverage artifact | Selected/visited/presented/cited IDs inform usage and audit artifacts. Coverage omission lists do not become query hits. |
| `continuation` | New `QueryContinuation` | Rebuild from snapshot, normalized request, ordering key, frontier, and visited IDs. Never wrap or reinterpret the StageView cursor. |
| `graph_digest`, `source_index_digest`, `provenance_ledger_digest` | Page/receipt lineage | Graph digest is explicit; source-index and ledger digests are receipt evidence metadata retained by the adapter until promoted to typed fields. |
| `content_digest` | `QueryReceipt.result_digest` | Recompute from the query page wire representation; do not copy a StageView digest over different content. |
| `locator_backend`, `fallback_backend` | `QueryReceipt.retrieval_backend`, `.fallback_backend` | Preserve the actual backend used, including deterministic fallback. |
| `blocking_records` | Truncation reason or typed error detail | Budget exclusions become explicit truncation; invalid/missing source references become typed errors. Never silently drop them. |
| `unresolved_conflict_ids` | Adapter diagnostic artifact | Not a normal query hit. Expose only through an explicit diagnostic operation added by a future version or retain in rollback output. |
| `missing_capabilities`, `capability_outcomes` | Adapter diagnostic artifact and telemetry | Record as operational evidence; do not pretend a missing capability is an empty query result. |
| `external_evidence`, `external_evidence_omissions` | Reading-stage input outside ArticleGraph query results | Preserve stage policy/provenance separately. It may enter an ArticleGraph `EvidenceEnvelope` only after it has canonical graph ownership and Source Plane locators. |

## Six-Stage Consumption Rule

Each stage begins with a small bootstrap and calls only permitted operations. Every
additional retrieval appends the stored receipt ID to the stage output. A stage may
temporarily obtain equivalent content through the StageView adapter, but parity is
measured by ordered identities, evidence, budgets, and receipts—not by byte-for-byte
equality with the old provider serialization.

The compatibility adapter remains available until all six stage regressions and
rollback verification pass. Removing it is outside this change unless those gates
are satisfied.
