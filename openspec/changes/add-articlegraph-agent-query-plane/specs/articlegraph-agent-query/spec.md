## ADDED Requirements

### Requirement: Unified public query surface
The system SHALL expose the same ArticleGraph query semantics through a public CLI and a Python service for search, locate, evidence, neighbors, claim tracing, and bounded context expansion.

#### Scenario: Equivalent CLI and Python query
- **WHEN** a caller submits equivalent normalized parameters to the CLI and Python service against the same snapshot
- **THEN** both interfaces return equivalent ordered hits, provenance, budgets, and continuation state

### Requirement: Provenance-complete typed results
Every query hit SHALL identify its graph or source objects, include the evidence used to produce the hit, state the match reason, and return all available source locators with an explicit locator-precision level.

#### Scenario: Page coordinates are unavailable
- **WHEN** a matching source unit has section and character-span provenance but no page or bounding box
- **THEN** the hit returns the section and character span, leaves page and bounding box null, and declares the achieved locator precision

### Requirement: Fail-closed evidence behavior
The query service SHALL NOT present graph-derived text or relations as grounded evidence when their referenced source objects cannot be resolved in the active snapshot.

#### Scenario: Dangling source reference
- **WHEN** a candidate hit contains a source reference that cannot be resolved
- **THEN** the service excludes or marks the hit as an integrity error and does not return it as supported evidence

### Requirement: Deterministic bounded execution
Each query SHALL enforce limits for result count, visited objects, traversal depth, evidence characters, and estimated exposed tokens, and SHALL report which limit caused truncation.

#### Scenario: Neighborhood exceeds budget
- **WHEN** neighbor expansion would visit more objects than the requested or server maximum permits
- **THEN** the service returns a deterministically ordered partial page, reports the object-budget truncation, and does not exceed the bound

### Requirement: Snapshot-safe continuation
Continuation tokens SHALL be opaque, versioned, bound to the graph snapshot and normalized query, and SHALL resume without duplicates or omissions under the same snapshot.

#### Scenario: Snapshot changes before continuation
- **WHEN** a caller presents a continuation token to a different graph snapshot
- **THEN** the service returns a typed restart-required error and does not continue against the new snapshot

### Requirement: Deterministic baseline without semantic dependencies
The mandatory query implementation SHALL support exact and lexical retrieval plus graph traversal without embeddings, external model calls, or an external graph database.

#### Scenario: Optional semantic backend is absent
- **WHEN** no semantic retrieval backend is configured
- **THEN** all public operations remain available with deterministic source-first behavior

### Requirement: Six-stage query receipts
When a six-stage reading step uses ArticleGraph, its output SHALL record query receipts that identify the snapshot, operation, normalized query digest, returned object IDs, budgets, and continuation usage.

#### Scenario: Stage retrieves additional evidence
- **WHEN** a reading stage calls the query service to expand its context
- **THEN** the stage artifact contains a receipt matching the executed query and returned graph/source objects
