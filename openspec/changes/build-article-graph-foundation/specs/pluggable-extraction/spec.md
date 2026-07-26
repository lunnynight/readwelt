## ADDED Requirements

### Requirement: Separate linguistic and semantic backend seams
The system SHALL support independently replaceable linguistic and semantic extraction backends with normalized descriptors and capability outcomes.

#### Scenario: Optional backend is unavailable
- **WHEN** an optional extraction backend is not installed
- **THEN** graph construction continues and records the affected capabilities as unsupported or failed

#### Scenario: Optional backend raises
- **WHEN** an optional backend raises during extraction
- **THEN** the build emits a failed extraction artifact and capability outcomes and continues with remaining or empty capabilities

#### Scenario: Empty differs from unsupported
- **WHEN** a backend successfully runs a supported capability and finds no candidates
- **THEN** the capability outcome is empty rather than unsupported

#### Scenario: Capability status reaches stage input
- **WHEN** a capability is empty, unsupported, failed, partial, or complete
- **THEN** the status is preserved through GraphExtraction, the aggregate capability report, and StageView without collapsing distinct states

### Requirement: Immutable raw graph extraction
Each extraction invocation SHALL emit an immutable `GraphExtraction` artifact containing backend identity, schema version, input unit IDs, candidate knowledge objects, grounding, confidence, ambiguity, warnings, and unresolved references.

#### Scenario: Candidate is preserved before merge
- **WHEN** a backend extracts two potentially equivalent entity mentions
- **THEN** both candidates remain present in the raw artifact regardless of later canonicalization

#### Scenario: Backend cannot mutate canonical graph
- **WHEN** an extraction backend completes
- **THEN** its output contains only raw candidates and no canonical graph mutation

#### Scenario: Extraction belongs to one revision
- **WHEN** extraction inputs contain units from different documents or snapshots
- **THEN** the backend rejects the batch rather than emitting an artifact with ambiguous revision identity

#### Scenario: Candidate epistemic status is required
- **WHEN** an extraction candidate omits its epistemic status
- **THEN** canonicalization rejects the candidate instead of defaulting it to explicit author content
