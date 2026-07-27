## ADDED Requirements

### Requirement: Versioned argument-locating taxonomy
ArticleGraph SHALL define a versioned, closed core taxonomy for machine locating candidates covering entity, concept, event, claim, premise, conclusion, evidence, example, objection, and qualification. It SHALL define typed core relations covering support, refutation, causation, contrast, qualification, exemplification, premise-to-claim, and conclusion flow. Extensions MUST be namespaced and unknown unnamespaced kinds or relations MUST fail empty or remain unresolved rather than silently entering the canonical graph.

#### Scenario: Extract an explicit objection and qualification
- **WHEN** a semantic backend emits an objection, a qualification, and their relation to a claim
- **THEN** GraphExtraction, canonicalization, SourceIndex, StageView, and provider provenance preserve their typed identities and source grounding without treating them as final Stage 2 conclusions

#### Scenario: Backend emits an unknown relation
- **WHEN** a backend emits an unversioned relation outside the core taxonomy
- **THEN** canonicalization retains a diagnostic and does not admit an arbitrary relation as a trusted core locating signal

### Requirement: Canonical confidence lineage
Every canonical node, edge, and claim SHALL expose a deterministic confidence assessment or an explicit unresolved confidence state, including the aggregation method and provenance back to candidate or mention assessments. Canonicalization MUST NOT discard the extraction confidence method.

#### Scenario: Two mentions have different confidence methods
- **WHEN** identity resolution combines two source-grounded mentions with different confidence scores or methods
- **THEN** the canonical node records the deterministic aggregation result and retains provenance to both original assessments

### Requirement: Argument taxonomy capability reporting
Backends SHALL declare which candidate kinds and relations they can emit. A claim-only fallback MUST report all unsupported argument kinds and relations as missing capabilities rather than making the ArticleGraph appear semantically complete.

#### Scenario: Deterministic fallback emits only claims
- **WHEN** the built-in fallback processes a document
- **THEN** source navigation remains complete, claim candidates remain advisory, and premise, conclusion, evidence, example, objection, qualification, and typed relation capabilities are reported as unavailable
