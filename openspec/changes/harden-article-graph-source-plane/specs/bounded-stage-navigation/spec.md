## ADDED Requirements

### Requirement: Hard provider-bound input budget
The system MUST enforce the configured token budget against the complete serialized packet that will be sent to the provider, including instructions, upstream artifacts, metadata, source excerpts, coverage data, and continuation state.

#### Scenario: Serialized packet reaches budget
- **WHEN** adding another source item would cause the provider-bound packet to exceed the hard budget
- **THEN** the item is omitted with a reason or split deterministically and the serialized packet remains within budget

#### Scenario: Stage request adds material after StageView
- **WHEN** anchors, retrieval hits, upstream claims, external evidence, metadata, or request provenance are added to a bounded StageView
- **THEN** the final serialized `StageRequest` is settled again against the same hard budget and cannot exceed it

#### Scenario: Provider envelope uses an auditable token counter
- **WHEN** a settled `StageRequest` is wrapped with provider instructions, user content, and a response schema
- **THEN** the complete provider input envelope is measured with a recorded provider-exact tokenizer or a declared conservative upper-bound counter and is revalidated against the same hard budget
- **AND** a byte-length heuristic that can underestimate the provider tokenizer MUST NOT be reported as a hard token bound

### Requirement: Resumable deterministic traversal
Every bounded StageView that does not exhaust its eligible traversal frontier SHALL return a continuation cursor bound to the document revision, Source Plane version, index digest, stage policy, and deterministic traversal state.

#### Scenario: Resume the next page
- **WHEN** a caller resumes with a valid continuation cursor
- **THEN** traversal continues deterministically without silently restarting or skipping the recorded frontier

#### Scenario: Reject stale cursor
- **WHEN** a cursor is used with another document revision or index digest
- **THEN** the system rejects it explicitly rather than returning mismatched source material

#### Scenario: Resume through the application runtime
- **WHEN** an Agent or replacement host resumes a persisted stage page
- **THEN** the application consumes the stored continuation/rescue state and sends the next deterministic bounded request instead of restarting at page one

#### Scenario: Decode a genuine historical navigation artifact
- **WHEN** a persisted pre-v2 cursor or stage-navigation artifact is opened
- **THEN** its original schema and digest are validated by a historical reader and it is either resumed under its historical contract or rejected explicitly without rewriting the payload

### Requirement: View coverage manifest
A StageView SHALL separately report visited, selected, serialized, presented-to-provider, cited, critical, and omitted source identities with omission reasons. Document source completeness MUST NOT be used as a substitute for StageView presentation completeness.

#### Scenario: Budget omits source units
- **WHEN** a StageView presents only part of a complete Source Plane
- **THEN** source coverage remains complete while view coverage is partial and all omitted eligible identities have reasons

#### Scenario: Critical anchor absent
- **WHEN** a required critical anchor is not presented to the provider
- **THEN** the StageView cannot claim complete stage input and reports the blocking or rescue state

#### Scenario: Critical range or element absent
- **WHEN** a required range, table, figure, caption, page image, or source-root element is not presented or its deterministic slices are incomplete
- **THEN** the StageView and stage settlement cannot claim complete input, and the typed identity is retained with an omission or continuation reason

#### Scenario: Enumerate every omitted source identity
- **WHEN** units, range/gap records, and non-text elements are omitted by policy, traversal state, or budget
- **THEN** the coverage manifest enumerates all three identity classes in deterministic order with exactly one explicit reason per omitted identity

#### Scenario: Stage candidate arrives before traversal is exhausted
- **WHEN** a provider returns a valid stage candidate while the StageView still has continuation, blocking records, or unresolved critical coverage
- **THEN** the persisted stage result retains the incomplete coverage and continuation state and cannot be represented as a fully settled stage conclusion

### Requirement: Progressive rescue ladder
The system SHALL support deterministic rescue from an initial packet through neighbor expansion, parent/child expansion, targeted retrieval, and section-complete paged traversal. Full-document presentation is permitted only when the complete serialized packet fits the hard budget.

#### Scenario: Semantic locator misses evidence
- **WHEN** semantic locating signals fail to include a required source anchor
- **THEN** the system can recover it through source-first structural, lexical, range, or paged traversal

#### Scenario: Long document fallback
- **WHEN** a document exceeds the provider budget
- **THEN** fallback uses bounded continuation or structural traversal and never requires normal full-text injection

### Requirement: Oversized source item handling
An individual source item that exceeds the remaining or maximum packet budget MUST be split at a deterministic source boundary with derived provenance or returned as an explicit blocking item. It MUST NOT be silently discarded.

#### Scenario: Oversized table
- **WHEN** a serialized table element exceeds the maximum StageView budget
- **THEN** the system returns deterministic table slices with shared source provenance or an explicit unsupported blocking result

### Requirement: Complete Source Plane traversal
Bounded stage navigation SHALL account for addressable text units, explicit range/gap records, and non-text source elements. Provider presentation MAY summarize whitespace gaps, but traversal and coverage MUST prove their reachability. Tables, figures, captions, and source-root artifacts MUST be selected, paged, sliced where supported, or explicitly blocked; they MUST NOT disappear because they lack a text unit.

#### Scenario: Image-only scanned PDF
- **WHEN** normalized text is empty but the Source Plane contains a preserved source-document element
- **THEN** bounded traversal visits and reports that element and the provider receives an addressable raw-source reference or explicit capability block

### Requirement: ArticleGraph remains an AI reading substrate
StageView SHALL present source facts, structural context, machine candidates, ambiguity, conflict, and provenance as locating material. It MUST NOT label ArticleGraph candidates as final conclusions about the article's main problem, argument, author model, validity boundary, or transferable principles.

#### Scenario: Stage 1 receives a claim candidate
- **WHEN** a machine-extracted claim is included in the Stage 1 view
- **THEN** it is labeled as a candidate with source evidence and the AI remains responsible for determining the article's main line

#### Scenario: Stage output references source
- **WHEN** a Stage 4 conclusion references an ArticleGraph item
- **THEN** it remains a stage conclusion and is not written back as an author-stated source fact

#### Scenario: Stage output cites a non-text source
- **WHEN** a stage conclusion is grounded only in a presented range, table, figure, page image, caption, source-root element, or ArticleGraph object
- **THEN** the provider schema, candidate parser, settlement, persisted claim, and provenance ledger preserve a typed citation without fabricating a text anchor

#### Scenario: Reject an unpresented typed citation
- **WHEN** a provider candidate cites a source or graph identity that was not admitted to the current provider-visible StageView or cannot close to the Source Plane
- **THEN** settlement rejects the citation fail-empty and the claim cannot be accepted

### Requirement: StageView-governed external evidence
External evidence SHALL enter a provider request only through a typed StageView admission carrying evidence identity, selection reason, provenance, and stage policy. Article-only stages MUST exclude it, and later stages MUST NOT receive unadmitted external evidence directly from an `EvidencePacket`.

#### Scenario: Evidence packet contains unadmitted external research
- **WHEN** an `EvidencePacket` contains external evidence that the current StageView did not admit
- **THEN** the final provider request excludes it and records the omission instead of bypassing StageView policy

### Requirement: Semantic failure does not break navigation
Failure or absence of semantic extraction MUST reduce locating hints only. It MUST NOT reduce Source Plane reachability or prevent bounded StageView traversal.

#### Scenario: No semantic graph objects
- **WHEN** a document has no accepted entity, relation, or claim candidates
- **THEN** all stages can still traverse the complete source through structural, ordinal, range, and lexical navigation
