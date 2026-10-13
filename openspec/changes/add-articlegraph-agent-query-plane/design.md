## Context

This design implements the **ArticleGraph Agent Reading MVP** defined by `product-prd.md`. At product level, ArticleGraph spans document intake, evidence modeling, agent query, reading orchestration, trust/observability, and evaluation. This change closes the missing query plane and connects those already-started planes into one measurable user journey.

ArticleGraph currently converts Xberg output into anchored source units, mentions, canonical nodes, edges, claims, provenance references, and an immutable artifact that can be projected into bounded `StageView` pages. This establishes a rebuildable evidence graph, but the only practical consumer path is sequential paging through internal structures. It lacks the task-oriented retrieval operations an agent needs to answer “where is this stated?”, “what supports this claim?”, “what is connected?”, and “what should I read next?” without loading the full document.

The design must work for heterogeneous Chinese research PDFs, preserve truthful source precision when page/bounding-box data is absent, remain useful without embeddings or a graph database, and support controlled experiments where infrastructure usage and costs are independently auditable.

## Goals / Non-Goals

**Goals:**

- Provide one stable query model shared by CLI, Python callers, and the six-stage reader.
- Make every returned assertion traceable to immutable graph/source objects and exact evidence.
- Bound result count, traversal depth, source bytes, and estimated token exposure.
- Preserve deterministic behavior and resumability within a graph snapshot.
- Enable a valid raw-versus-ArticleGraph A/B experiment on real documents.

**Non-Goals:**

- Replacing Xberg as the primary structured-cleaning backend.
- Introducing Neo4j, RDF, GraphRAG global search, a corpus-wide knowledge graph, or a mandatory embedding service.
- Solving domain ontology governance or cross-document entity resolution.
- Claiming reading-quality improvement before the controlled evaluation passes its validity gates.

The normative public operation semantics, error behavior, and field-by-field
`StageView` compatibility mapping are defined in
[`query-contract.md`](query-contract.md).

## Decisions

### 1. Add a query service over the canonical snapshot

`ArticleGraphQueryService` will read an immutable ArticleGraph artifact plus its `SourceIndex`. It will expose typed operations: `search`, `locate`, `evidence`, `neighbors`, `trace_claim`, and `expand_context`. The CLI and six-stage pipeline are adapters over this service, not independent query implementations.

This keeps semantics consistent across consumers and preserves the current rebuildable-file architecture. A graph database was rejected because document-scoped traversal does not yet justify an operational store and would not solve the missing public contract.

### 2. Use source-first hybrid retrieval

The mandatory retrieval path is deterministic lexical/identifier filtering over source units, nodes, claims, and relations, followed by graph expansion. Optional semantic ranking can contribute candidates behind the same interface, but results remain valid when it is absent and semantic scores never replace provenance.

This makes the first implementation testable and cheap. Embedding-only retrieval was rejected because exact wording and location are first-class benchmark tasks, and because it adds model/version drift before the baseline is established.

### 3. Return a common evidence envelope

All operations return a `QueryPage` containing ordered `QueryHit` records. A hit carries graph/source IDs, object kind, matched text or exact evidence excerpt, match reason, relation path where applicable, epistemic status, ambiguity/confidence, locator precision, and source references. Page, section, element, character span, and bounding box fields are nullable independently; unavailable coordinates remain null and are never inferred.

The page also carries snapshot digest, query digest, applied budgets, estimated exposed tokens, truncation reasons, and an opaque continuation token. This common envelope prevents stage-specific ad hoc structures.

### 4. Make continuations snapshot-bound and stateless

Continuation tokens encode or securely reference the snapshot digest, normalized query digest, operation, deterministic ordering key, and remaining traversal state. A token is rejected if the snapshot or query differs. The service does not silently continue against rebuilt content.

Offset-only pagination was rejected because graph expansion and ranked retrieval can reorder after rebuilds and produce duplicates or omissions.

### 5. Enforce budgets inside the service

Every query specifies bounded limits with server-side maxima for hits, traversal depth, visited objects, evidence characters, and estimated tokens. Stable tie-breaking uses score, source order, object kind, and stable ID. When any bound is reached, the response is partial but explicit and resumable where meaningful.

Agent-prompt-only budgeting was rejected because callers cannot reliably predict graph fan-out or serialized evidence size.

### 6. Integrate the six stages through query intents

Each reading stage receives a small stage bootstrap plus access to permitted query operations. Stages request evidence incrementally and record query receipts in their outputs. Existing eager `StageView` generation remains a compatibility adapter during migration, then becomes an implementation detail of `expand_context` rather than the product API.

This change defines the consumption contract; it does not yet redesign each stage's reasoning prompt or assert that all six stages are optimized.

The migration exposure accounting and its explicit no-quality-claim boundary are
recorded in `stage-context-exposure.md`.

### 7. Gate A/B conclusions on experimental validity

Baseline and treatment use the same source document, task set, model, model settings, wall-clock policy, and answer schema. The treatment receives ArticleGraph access; the baseline does not. Runs record model usage, elapsed time, tool trajectories, query receipts, preprocessing amortization, and evaluator evidence. A treatment run without direct matching query receipts is invalid, as is a run without a final parseable answer.

Scores separately cover location precision/recall, citation correctness, comprehension accuracy, latency, input/output/cache tokens, and cold/warm infrastructure cost. Aggregate winner claims require a preregistered stratified sample rather than one convenient PDF.

## Risks / Trade-offs

- [Lexical retrieval misses paraphrases] → Preserve a pluggable semantic-candidate hook and measure lexical recall before making it mandatory.
- [Graph fan-out creates large responses] → Enforce depth, object, character, and token budgets with explicit truncation.
- [Xberg lacks page or bounding-box data] → Return the strongest available locator and its precision level; never fabricate coordinates.
- [Opaque cursors become incompatible] → Version tokens and fail with a typed restart-required error.
- [Six-stage migration changes behavior] → Keep the existing `StageView` adapter until parity tests pass.
- [Benchmark favors cached treatment artifacts] → Report cold build, warm query, and amortized costs separately.
- [Domain kinds remain inconsistent] → Treat kinds as filterable labels in this change; address ontology governance separately.

## Migration Plan

1. Add query/result schemas and service over existing artifacts without changing graph generation.
2. Add CLI and Python adapters plus contract tests.
3. Route one six-stage consumer through the service while retaining the existing `StageView` path for comparison.
4. Migrate remaining stages after parity and budget tests pass.
5. Run the preregistered pilot, then the stratified A/B benchmark; publish results only when validity gates pass.

Rollback consists of disabling the new adapters and retaining existing graph artifacts and `StageView` consumption; no stored artifact migration is required initially.

## Open Questions

- What maximum default token and evidence-character budgets should be exposed per stage after pilot measurements?
- Which optional semantic backend, if any, earns inclusion after the deterministic baseline is measured?
- Should cross-document querying become a separate corpus-query capability after document-scoped evaluation?
