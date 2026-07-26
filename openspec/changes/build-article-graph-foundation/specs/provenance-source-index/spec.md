## ADDED Requirements

### Requirement: Independent append-only provenance ledger
The system SHALL record content-addressed provenance events for unitization, extraction, grounding, canonicalization, conflicts, and derived projections without depending on the canonical graph as the ledger.

#### Scenario: Ledger chain integrity
- **WHEN** provenance events are appended
- **THEN** each event records its sequence and previous digest so the chain can be verified

#### Scenario: Grounding fails empty
- **WHEN** a source-required candidate has no valid source anchor
- **THEN** the system rejects or defers it and records the grounding failure rather than inventing an anchor

#### Scenario: Candidate names an unknown text unit
- **WHEN** a backend candidate claims grounding in a unit outside the current unitization result
- **THEN** the raw extraction remains auditable but the candidate is rejected from ArticleGraph and a grounding event and merge rejection are recorded

#### Scenario: Provenance closure
- **WHEN** a knowledge object is admitted to ArticleGraph or StageView
- **THEN** its lineage resolves through canonicalization and raw extraction to an anchored source unit or an explicitly non-source epistemic status

#### Scenario: Deterministic ledger build
- **WHEN** a document build is replayed with identical source capture time and inputs
- **THEN** ledger event timestamps, ordering, event digests, head digest, and durable ledger digest are identical

### Requirement: Bidirectional source index
The system SHALL materialize a rebuildable index from knowledge nodes, edges, and claims to source units and from source units back to those knowledge objects.

#### Scenario: Knowledge to original text
- **WHEN** a stage selects a canonical claim
- **THEN** the source index resolves the claim to its evidence text units and exact source anchors

#### Scenario: Original text to knowledge
- **WHEN** a caller selects an anchored text unit
- **THEN** the source index returns all canonical nodes, edges, and claims grounded in that unit

#### Scenario: Projection cannot create grounding
- **WHEN** a projection or unrelated ledger event names a knowledge object and an unknown source unit
- **THEN** rebuilding SourceIndex does not add that unit to the object's factual grounding
