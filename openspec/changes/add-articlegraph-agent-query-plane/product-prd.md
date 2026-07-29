# ArticleGraph Product PRD

## Product Definition

ArticleGraph is Readwelt's evidence-grounded document intelligence substrate for AI agents. It converts heterogeneous long documents into a stable, queryable, traceable reading environment so an agent can find, understand, relate, and cite information without repeatedly loading or rereading the entire source.

ArticleGraph is not merely a graph file, extraction pipeline, pagination utility, or retrieval command. Those are implementation capabilities beneath the product contract.

## Product Problem

General-purpose agents can technically open documents, but long-document work remains expensive and unreliable:

- the agent repeatedly scans large sources and spends tokens rediscovering structure;
- answers are difficult to trace back to exact source evidence;
- location tasks degrade when page, section, or layout metadata is incomplete;
- every reading workflow reinvents search, chunking, context assembly, and citation;
- infrastructure can appear available without being used, making benchmark claims invalid;
- preprocessing cost, warm reuse value, and comprehension quality are rarely measured together.

Readwelt needs a reusable product layer that makes documents operationally readable by agents, rather than another one-off document parser or graph representation.

## Product Users

### Primary: Reading Agent

Needs to discover relevant passages, navigate document structure, follow claims and relations, request more context, and return grounded answers within a bounded context budget.

### Secondary: Workflow or Stage Author

Needs a stable contract for building multi-stage reading and research workflows without knowing Xberg internals, graph serialization, or source-index implementation details.

### Secondary: Operator and Evaluator

Needs to ingest documents, inspect graph health, reproduce a query, audit evidence lineage, measure cost and latency, and determine whether ArticleGraph improved an agent outcome.

## Product Promise

For a supported document, ArticleGraph SHALL let an agent:

1. establish what the document contains without reading it in full;
2. locate relevant language at the strongest truthful source precision available;
3. retrieve the exact evidence behind a claim or relation;
4. expand along document structure and graph relationships under an explicit budget;
5. produce an answer whose supporting path can be replayed and audited;
6. reuse the prepared document across tasks so repeated reading becomes cheaper and faster.

## Product Capability Map

### 1. Document Intake Plane

Accept heterogeneous source documents, use Xberg as the primary structural-cleaning backend, preserve source identity, and expose extraction limitations rather than hiding them.

### 2. Evidence Model Plane

Build the canonical document-scoped ArticleGraph: anchored source units, mentions, nodes, edges, claims, and provenance references with deterministic identities and integrity checks.

### 3. Agent Query Plane

Provide task-oriented search, location, evidence, relationship, claim-trace, and bounded expansion operations through stable public interfaces.

### 4. Reading Orchestration Plane

Let Readwelt's six stages consume ArticleGraph incrementally through query intents and receipts instead of eagerly receiving an entire graph or document.

### 5. Trust and Observability Plane

Make every output replayable from immutable source and graph identities; record query paths, budgets, truncation, failures, and achieved locator precision.

### 6. Evaluation Plane

Measure whether the complete product improves location, understanding, citation quality, latency, and token economics against matched raw-document baselines.

## Product Boundary

ArticleGraph owns document preparation, evidence identity, document-scoped query/navigation, reading-context delivery, provenance, and usage telemetry.

ArticleGraph does not own the upstream source format, the reasoning model, a universal domain ontology, corpus-wide truth resolution, or the final business workflow. Those systems consume or extend ArticleGraph through explicit contracts.

## Product-Level Success Criteria

The product is not successful merely because a graph can be built or paged. A release candidate SHALL demonstrate all of the following on a preregistered, stratified real-document corpus:

- **Coverage:** supported documents can be ingested and queried, with failures and degraded locator precision reported explicitly.
- **Grounding:** returned claims and relations resolve to source evidence; unsupported evidence fails closed.
- **Task effectiveness:** assisted agents improve or preserve location and comprehension quality relative to the raw baseline.
- **Efficiency:** warm repeated tasks reduce agent-visible document volume, token use, or time; cold build cost is reported separately.
- **Usability:** an agent can discover and use the public query surface without guessing internal file layouts or commands.
- **Reproducibility:** answers, queries, continuations, and benchmark conclusions can be replayed against immutable snapshots.
- **Operational fitness:** concurrent ingestion and query workloads have measured throughput, resource bounds, and failure recovery behavior.

No product-improvement claim SHALL be made when treatment use is unproven, final answers are missing, comparison conditions differ, or only a single convenient document was tested.

The measurable owners, datasets, thresholds, evidence bundle, and GO/NO-GO rule for
the Agent Reading MVP are defined in [`release-gates.md`](release-gates.md).

## Current Product Maturity

| Product plane | Current state | Release gap |
|---|---|---|
| Document Intake | Xberg-backed and exercised | corpus-level robustness and throughput characterization |
| Evidence Model | canonical graph and provenance exist | ontology governance and broader integrity coverage |
| Agent Query | internal pagination only | public task-oriented query contract and implementation |
| Reading Orchestration | partial `StageView` integration | query-driven optimization of all six stages |
| Trust and Observability | artifact provenance exists | end-to-end query receipts and replay tooling |
| Evaluation | pilot harness exists | valid stratified A/B evidence and product thresholds |

## Release Strategy

The next product increment is **ArticleGraph Agent Reading MVP**. It closes the Agent Query Plane, connects it to the six-stage reader, and proves the complete product loop through a validity-gated experiment. Semantic retrieval, cross-document graphs, and domain ontology expansion remain later increments unless the MVP measurements show they are necessary.
