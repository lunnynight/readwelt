## ADDED Requirements

### Requirement: Open-source adoption record
Before implementing a parser, structural projector, chunker, provenance mechanism, retrieval algorithm, canonicalizer scorer, or linguistic extractor in-house, the project SHALL record evaluated open-source candidates, exact revisions, code licenses, model/data licenses, measured capabilities, integration weight, and the adopt/adapt/reject decision.

#### Scenario: Propose a custom Chinese tokenizer
- **WHEN** an implementation task proposes a new Chinese tokenizer
- **THEN** the adoption record first compares eligible HanLP, PaddleNLP, Stanza, and authorization-compatible LTP capabilities

### Requirement: Thin adapter preference
When an open-source component satisfies a required capability, Readwelt MUST integrate it through the narrowest stable adapter that preserves Source Plane and provenance contracts. The project MUST NOT reimplement the capability solely to avoid an adapter.

#### Scenario: Reuse native structural references
- **WHEN** Docling Core provides required page, bbox, charspan, reference, or hierarchical iteration behavior absent from Xberg
- **THEN** the design evaluates an optional thin adapter before implementing an equivalent parser subsystem

### Requirement: Product runtime exclusion
Adopting an interface or algorithm SHALL NOT implicitly adopt the source project's product ontology, agent workflow, LLM pipeline, storage system, or global search behavior.

#### Scenario: Reuse GraphRAG reverse mapping
- **WHEN** Readwelt adopts the TextUnit reverse-map algorithm
- **THEN** community summarization, global search, and LLM graph extraction remain excluded unless separately specified

#### Scenario: Reuse KAG source edges
- **WHEN** Readwelt adopts explicit knowledge-to-source-chunk relationships
- **THEN** KAG project, SchemaClient, reasoner, and `SubGraph` runtime are not required dependencies

### Requirement: Pinned dependency provenance
Every adopted backend or copied/adapted algorithm SHALL record its source repository, exact revision, license decision, local adapter version, and capability scope in build or artifact provenance.

#### Scenario: Backend artifact produced
- **WHEN** an optional structural or linguistic backend contributes records
- **THEN** the artifact identifies the backend revision, adapter version, model identity where applicable, and declared capabilities

#### Scenario: Docling fallback contributes Source Plane structure
- **WHEN** the production Docling PDF/OCR fallback contributes text or structure to a build
- **THEN** immutable build lineage records the exact dependency versions, adapter version, local model-tree digest and revisions, code/model license decisions, OCR configuration, capability scope, trigger, and remote-service/plugin exclusions

#### Scenario: Adapted source-index algorithm contributes an artifact
- **WHEN** a copied or adapted GraphRAG, KAG, Docling, PROV, or OpenLineage pattern contributes to a build artifact
- **THEN** build or artifact provenance records repository, exact revision, license decision, local adapter version, adopted capability scope, and excluded product behavior

### Requirement: Initial backend boundaries
The default adoption plan SHALL keep Xberg as primary ingestion, evaluate Docling Core as an optional structural fallback, adapt Docling Graph provenance/merge patterns without importing its product graph, adapt GraphRAG/KAG source-index patterns without their runtimes, and run a Chinese backend bake-off before choosing a default semantic preprocessor. DeepKE SHALL remain schema/output reference only; Splink SHALL remain an optional mention-pair scorer; PROV and OpenLineage SHALL remain interoperability layers.

#### Scenario: DeepKE default integration proposed
- **WHEN** a task proposes DeepKE or OneKE as the default ArticleGraph extractor
- **THEN** the proposal is rejected unless a new measured adoption record demonstrates a stable unified API, acceptable resources, and superiority over the bake-off candidates

#### Scenario: LTP default integration proposed
- **WHEN** a task proposes LTP as a default distributed backend
- **THEN** its code, model, and commercial authorization constraints are resolved before adoption

### Requirement: Production-callable locating backends
Measured backend candidates SHALL remain benchmark-only until a production adapter exposes their declared capabilities through `ArticleGraphBuilder` with pinned dependency/model provenance and explicit capability outcomes. The completed ArticleGraph runtime SHALL provide a production-callable structural fallback for formats whose primary parser exposes no structure, a production-callable Chinese linguistic adapter, and a semantic adapter capable of emitting the versioned argument-locating taxonomy. Missing models or optional dependencies MUST degrade explicitly without reducing Source Plane reachability.

#### Scenario: Xberg exposes no PDF structure
- **WHEN** the pinned Xberg adapter returns content but no page, table, figure, caption, or hierarchy records for a PDF
- **THEN** a measured optional structural fallback is invoked when configured, and its records and failures are attributed separately without replacing the original source root

#### Scenario: Optional Chinese or semantic backend is unavailable
- **WHEN** its dependency, model, license authorization, or runtime is unavailable
- **THEN** the build emits a typed capability failure, preserves deterministic source-first operation, and does not pretend that the missing locating candidates were extracted
