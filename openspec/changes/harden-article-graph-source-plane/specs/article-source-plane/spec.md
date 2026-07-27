## ADDED Requirements

### Requirement: Complete normalized source reachability
The system SHALL preserve the complete normalized source artifact and SHALL resolve every normalized source range to an addressable text unit or explicit source range record. Whitespace and separators MAY remain outside semantic text units, but they MUST remain range-addressable and reconstructable.

#### Scenario: Reconstruct normalized text
- **WHEN** a Source Plane is built from a document revision
- **THEN** ordered text-unit and range records reconstruct the exact normalized artifact without an unrecorded gap

#### Scenario: Resolve separator offset
- **WHEN** a caller locates an offset inside a paragraph separator
- **THEN** the Source Plane returns an explicit range record and its adjacent units rather than reporting the offset as uncovered

### Requirement: Complete source element preservation
The system SHALL create a stable source element record for every text or non-text element exposed by an ingestion backend. An unsupported semantic or layout capability MUST be recorded as unavailable without discarding the raw element, serialized payload handle, native reference, or reading position.

#### Scenario: Unsupported table interpretation
- **WHEN** the parser exposes a table element but no cell semantics
- **THEN** the Source Plane preserves an addressable table element and records the missing table-semantics capability

#### Scenario: Figure without geometry
- **WHEN** an EPUB exposes a figure and caption without page geometry
- **THEN** both elements and their available relationship remain addressable while geometry is explicitly unavailable

#### Scenario: Empty normalized extraction from a binary document
- **WHEN** a scanned PDF or container document yields no normalized text
- **THEN** the immutable original source bytes remain a content-addressed source-root element, document identity remains bound to those bytes, and the missing text/layout capability is reported instead of collapsing distinct files into one empty-text identity

### Requirement: Deterministic source identities and traversal
For the same document revision and Source Plane schema, the system MUST produce stable source identities and deterministic reading order. Starting at the document root, a caller SHALL be able to traverse all source items in finite ordered steps.

#### Scenario: Deterministic rebuild
- **WHEN** the same revision is rebuilt twice with identical backend outputs and policy
- **THEN** source identities, order, parent/child references, and artifact digests are identical

#### Scenario: Traverse an entire long document
- **WHEN** a caller repeatedly follows the ordered traversal from the document root
- **THEN** every source item is visited exactly as recorded without requiring full-text prompt injection

#### Scenario: Reject a closed but untraversable structure
- **WHEN** source-element references form a parent cycle, a neighbor cycle, more than one source root, or a closed subgraph disconnected from the source root
- **THEN** Source Plane validation fails explicitly even if every individual reference resolves to an existing identity

### Requirement: Structure preservation without fabrication
The system SHALL preserve native parent, child, previous, next, page, heading, table, figure, caption, and reading-order relationships when available. Missing or ambiguous relationships MUST be represented as capability gaps or unresolved projections and MUST NOT be guessed.

#### Scenario: Repeated paragraph text
- **WHEN** identical paragraph text occurs at multiple native element positions
- **THEN** projection uses native identity, occurrence, offset, or order evidence and does not attach both occurrences to one structure record

#### Scenario: Nodes and elements coexist
- **WHEN** Xberg exposes both document nodes and elements
- **THEN** the adapter consumes their non-duplicate information cumulatively instead of discarding one collection

#### Scenario: Ambiguous exact-text fallback
- **WHEN** no native identity or offset exists and exact-text matching has multiple candidates
- **THEN** the projection is recorded as unresolved with candidate evidence rather than fabricated

#### Scenario: Present structure to a reading stage
- **WHEN** a StageView admits a source element with child or typed structural relations
- **THEN** the provider-visible element includes the actual child identities and relation type/target identities under the same budget, while counts and digests verify that projection

### Requirement: Source-first indexes
The SourceIndex SHALL provide deterministic source-first lookup by normalized range, ordinal, section, heading, native element, page, and available lexical locator results. These indexes MUST remain usable when all semantic extraction backends fail.

#### Scenario: Semantic backend failure
- **WHEN** entity, relation, and claim extraction all fail for a document
- **THEN** callers can still locate and traverse every source item through structural, ordinal, range, and lexical indexes

#### Scenario: Bidirectional knowledge grounding
- **WHEN** a canonical knowledge object has grounded source evidence
- **THEN** it resolves to source units, ranges, or source elements and those source records resolve back to the knowledge object

#### Scenario: Every SourceIndex projection remains closed
- **WHEN** section, heading, page, lexical, parent/child, previous/next, range, element, unit, or knowledge projections are rebuilt
- **THEN** every key and value resolves to a typed Source Plane or canonical identity, every declared bidirectional projection agrees in both directions, and an injected unknown identity fails closure

### Requirement: Fail-empty source grounding
An unresolved source reference MUST return an explicit empty or unresolved result with diagnostics. The system MUST NOT invent a source association to satisfy provenance or index closure.

#### Scenario: Unknown native reference
- **WHEN** an extraction candidate refers to a native element that is absent from the Source Plane
- **THEN** canonicalization retains the unresolved diagnostic and creates no false source edge

#### Scenario: Known non-text element is the only source grounding
- **WHEN** an extraction candidate is grounded to a known table, figure, page image, caption, or source-root element and has no projected text unit
- **THEN** canonicalization admits the candidate as a source-grounded locating signal, retains its source-element identity through ArticleGraph, SourceIndex, StageView, and provenance, and does not fabricate a text-unit association

### Requirement: Versioned source coverage manifest
Each Source Plane artifact SHALL include a versioned coverage manifest that separately reports normalized-range coverage, source-element preservation, structural capabilities, unresolved projections, and unsupported backend capabilities.

#### Scenario: Partial parser capability
- **WHEN** a parser preserves text and reading order but exposes no page geometry
- **THEN** range and traversal coverage are complete while page-geometry capability is unavailable

### Requirement: Versioned aggregate Source Plane artifact
The aggregate Source Plane schema MUST change when source ranges, elements, coverage dimensions, or identity semantics change. Current readers SHALL distinguish historical text-unit-only artifacts from the complete Source Plane and SHALL semantically validate internal identities and digests when decoding either version.

#### Scenario: Read a historical unitization artifact
- **WHEN** a historical text-unit-only artifact is opened by a current reader
- **THEN** it is decoded under its historical schema without inventing current ranges/elements and without rewriting its immutable bytes

#### Scenario: Build the complete Source Plane
- **WHEN** current ingestion produces ranges, elements, raw source identity, and a coverage manifest
- **THEN** the aggregate artifact uses a newer schema version and continuation cursors bind to that exact version
