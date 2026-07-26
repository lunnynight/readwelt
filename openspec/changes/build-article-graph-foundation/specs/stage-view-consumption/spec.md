## ADDED Requirements

### Requirement: Budgeted explainable StageView
The system SHALL project a stage-specific view from ArticleGraph build output, stage context, upstream state, and a token budget.

#### Scenario: Stage selects minimal grounded context
- **WHEN** a stage requests a view under a token budget
- **THEN** the view contains selected knowledge, source units, token estimate, and a reason for every selection

#### Scenario: Missing capability is visible
- **WHEN** required graph information is absent because an extraction capability failed or was unsupported
- **THEN** the StageView reports the missing capability rather than treating the article as lacking that information

### Requirement: Incremental six-stage consumption
The stage engine SHALL be able to consume StageView while retaining the existing SemanticAtlas path only as an explicitly labeled migration fallback.

#### Scenario: Fallback locator is used
- **WHEN** graph coverage is insufficient during migration
- **THEN** SemanticAtlas may locate anchored source units and the StageView labels those selections as fallback

#### Scenario: Knowledge remains traceable through stage input
- **WHEN** a stage receives a selected node, edge, or claim
- **THEN** the stage input can navigate through SourceIndex and ProvenanceLedger to raw extraction and original source

#### Scenario: StageView lineage is explicit
- **WHEN** a StageView is persisted or sent to an Agent
- **THEN** it carries the graph, source-index, and provenance-ledger digests from which it was projected
