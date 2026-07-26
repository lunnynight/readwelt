## ADDED Requirements

### Requirement: Deterministic canonicalization
The system SHALL deterministically perform identity resolution, relation reconciliation, and claim assembly from raw extraction artifacts and a versioned policy.

#### Scenario: Repeated canonicalization
- **WHEN** identical artifacts, policy, and schema version are canonicalized repeatedly
- **THEN** the graph, decisions, conflicts, and merge report have identical content digests

### Requirement: Explicit merge decisions and conflicts
Every candidate identity decision MUST be represented as merge, keep-separate, defer, or reject with reasons, evidence references, policy identity, and confidence.

#### Scenario: Ambiguous identity
- **WHEN** the canonicalizer lacks sufficient evidence to merge two mentions
- **THEN** it emits a deferred decision or conflict and preserves both mentions

#### Scenario: Same label is not identity evidence
- **WHEN** same-kind mentions share a normalized label but are grounded in different source units without additional identity evidence
- **THEN** the canonicalizer defers or keeps them separate rather than destructively merging them

#### Scenario: Rejected candidate
- **WHEN** a candidate is rejected by grounding or schema policy
- **THEN** the rejection remains traceable in the merge report and provenance ledger

### Requirement: Epistemic separation
Every canonical knowledge object SHALL distinguish explicit author content, linguistic inference, semantic inference, and canonicalization, and SHALL reserve distinct statuses for later internal derivation, external research, and synthesis.

#### Scenario: Canonical entity derived from mentions
- **WHEN** multiple explicit mentions are merged into a canonical entity
- **THEN** the mentions remain explicit and the canonical entity is labeled canonicalized

#### Scenario: Completion output cannot masquerade as source
- **WHEN** a later synthesized assertion is attached to the knowledge space
- **THEN** it cannot be labeled as explicit author content

### Requirement: Deep deterministic build interface
The application SHALL construct unitization, raw extraction, canonical graph, merge report, provenance ledger, source index, and capability report through one versioned ArticleGraph build interface.

#### Scenario: Identical build input
- **WHEN** the same source revision, normalized text, backend outputs, build policy, and schema versions are processed repeatedly
- **THEN** every build artifact and the aggregate build result have identical content digests

#### Scenario: Upstream digest changes
- **WHEN** a source, extraction, policy, or schema digest changes
- **THEN** dependent graph and stage projections are invalidated without rewriting immutable prior artifacts
