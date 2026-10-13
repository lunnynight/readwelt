## Purpose

帮助读者从文章已经留下的证据出发，重新展开使作者能够提出该问题、采取该视角并写成当前论证的现实与知识条件，而不是把背景资料再次压缩成摘要。

## ADDED Requirements

### Requirement: Reconstruct the conditions that generate the article

The reading result MUST represent an author-world explanation as a bounded chain from relevant world conditions to the problem the author addresses and from that problem to the article's selected concepts, distinctions, evidence, or argumentative moves. Each link MUST identify the supporting source material or be marked as an interpretation whose evidence is insufficient.

#### Scenario: A settled explanation connects world and text
- **WHEN** the reading stages have settled claims about a relevant condition, the problem it makes salient, and an article choice responding to that problem
- **THEN** the reader report MUST present those items as a connected explanation in that order and MUST retain the identifiers needed to trace each item to its supporting material

#### Scenario: The source does not establish a causal link
- **WHEN** a condition is relevant to the article but the available source and admitted external evidence do not establish why it generated the problem or article choice
- **THEN** the system MUST present the relation as an open gap or qualified interpretation and MUST NOT state it as an established author fact

### Requirement: Separate source fact, external context, and interpretation

The reading result MUST distinguish article-explicit material, admitted external context, and model interpretation for every author-world item and relation. External context MUST NOT rewrite the settled article mainline or argument structure.

#### Scenario: External context expands but does not replace the article
- **WHEN** an external source explains a concept, institution, or historical condition omitted by the article
- **THEN** the system MAY include that context in the author-world explanation, but MUST label its provenance and MUST preserve the article's original claims and structure unchanged

#### Scenario: Competing world explanations remain possible
- **WHEN** two or more interpretations explain the author's problem or choice and the evidence cannot select one
- **THEN** the result MUST retain the competing interpretations separately, identify their evidence and uncertainty, and MUST NOT collapse them into one author intention

### Requirement: Publish a reader-facing causal explanation

The completed reader report MUST include a section that explains how the reconstructed world conditions make the article's question and form intelligible. The section MUST include unresolved gaps and limitations when the chain is incomplete, and MUST not publish unsettled or rejected claims as established conclusions.

#### Scenario: Complete author-world section is rendered
- **WHEN** publishable author-world items and relations exist in the settled reading bundle
- **THEN** the report MUST render the causal chain before or alongside the detailed world conditions and MUST include traceable references to the related article claims

#### Scenario: Author-world reconstruction is underdetermined
- **WHEN** the bundle contains no settled causal chain or contains only unresolved author-world claims
- **THEN** the report MUST say that the author's world cannot yet be reconstructed with the available evidence and MUST expose the relevant gap rather than inventing a background narrative
