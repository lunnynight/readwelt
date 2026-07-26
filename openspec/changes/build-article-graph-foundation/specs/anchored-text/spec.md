## ADDED Requirements

### Requirement: Revision-aware anchored text units
The system SHALL transform each source snapshot into ordered `AnchoredTextUnit` records that retain document revision, structure, exact text, content hash, navigation references, and source anchors.

#### Scenario: Structured paragraph is unitized
- **WHEN** a source snapshot contains a paragraph with a structural path and source span
- **THEN** the resulting text unit retains the exact paragraph text, revision identity, structural path, ordinal, kind, hash, and source span

#### Scenario: Stable identity within a revision
- **WHEN** the same snapshot and unitization schema are processed repeatedly
- **THEN** the system produces identical text-unit identifiers and content digests

### Requirement: Explicit source coverage
The system MUST account for every non-whitespace source range as covered, unsupported, or uncovered and MUST record normalization transformations.

#### Scenario: Unsupported source element
- **WHEN** Xberg exposes an element that the unitizer cannot represent
- **THEN** the coverage report identifies that element and does not silently discard it

#### Scenario: Complete plain-text coverage
- **WHEN** a plain-text snapshot is unitized successfully
- **THEN** all non-whitespace character ranges are covered by anchored text units

#### Scenario: Normalization is auditable
- **WHEN** unitization consumes normalized text that differs from the source representation
- **THEN** the coverage artifact records every known normalization transformation rather than treating normalized bytes as untouched source
