## Why

ArticleGraph must become Readwelt's evidence-grounded document intelligence product for AI agents, not stop at producing a traceable graph artifact. The current build and pagination foundation covers only part of that promise: the first real-document benchmark showed that agents still lack a usable way to understand, locate, expand, and cite document evidence within a bounded budget.

## What Changes

- Introduce one stable ArticleGraph query surface for both CLI and programmatic callers, covering search, exact location, evidence retrieval, graph-neighbor expansion, claim tracing, and resumable bounded context expansion.
- Establish the product capability map and end-to-end promise spanning document intake, evidence modeling, agent query, six-stage reading orchestration, trust/observability, and evaluation.
- Return typed, provenance-complete results with stable object IDs, verbatim evidence, truthful locators, match rationale, epistemic status, ambiguity/confidence, snapshot identity, and continuation metadata.
- Define deterministic ordering, explicit result/token budgets, snapshot-bound cursors, and fail-closed behavior when requested provenance or locator precision is unavailable.
- Define how the six-stage reading pipeline consumes the query plane instead of receiving an eagerly materialized graph dump.
- Add a controlled A/B benchmark contract comparing raw-document agents with ArticleGraph-assisted agents on the same real documents, model, tasks, and budgets, including direct evidence that the treatment actually used ArticleGraph.
- No graph database, global corpus reasoner, or domain ontology is introduced by this change.

## Capabilities

### New Capabilities

- `articlegraph-agent-query`: Public CLI and Python query contracts for bounded, traceable search, location, evidence, neighborhood, claim-trace, and continuation operations over an immutable ArticleGraph snapshot.
- `articlegraph-reading-evaluation`: Reproducible, validity-gated A/B evaluation of ArticleGraph-assisted document location and understanding against raw-document baselines.

### Modified Capabilities

None. The existing ArticleGraph requirements remain recorded in historical changes and no stable capability currently exists under `openspec/specs/` to modify.

## Impact

- Affects ArticleGraph source indexing, graph traversal, `StageView` integration, CLI registration, Python-facing service contracts, schemas, and documentation.
- Adds query-result and continuation-token schemas while preserving existing graph artifacts and build behavior.
- Adds benchmark fixtures, treatment-usage telemetry, validity checks, and regression tests using stratified documents from the real `“海量”专题` corpus.
- Uses `product-prd.md` as the product-level acceptance frame; this change delivers the Agent Reading MVP within that broader architecture.
- The initial implementation remains local and deterministic; optional semantic indexes or external graph stores may be added later only behind the same public contract.
