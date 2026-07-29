## ADDED Requirements

### Requirement: Controlled baseline and treatment
The benchmark SHALL compare raw-document and ArticleGraph-assisted agents using the same document, tasks, model, model settings, answer schema, and execution policy, with ArticleGraph access as the treatment variable.

#### Scenario: Matched pair execution
- **WHEN** a document-task pair is scheduled for evaluation
- **THEN** the harness produces matched baseline and treatment run records that differ only in the declared infrastructure exposure

### Requirement: Real stratified document sample
The benchmark SHALL draw a preregistered sample from the real `“海量”专题` corpus across document categories, lengths, and extraction-quality strata, and SHALL preserve immutable document digests.

#### Scenario: Sample manifest is created
- **WHEN** a benchmark round begins
- **THEN** its manifest records selection strata, source digests, tasks, scoring rules, and exclusion criteria before scored runs execute

### Requirement: Location and comprehension scoring
The benchmark SHALL score evidence-location correctness separately from document-comprehension correctness using gold evidence anchors and answer rubrics.

#### Scenario: Correct answer cites wrong location
- **WHEN** an agent gives a semantically correct answer but its cited evidence does not match the gold or accepted source anchor
- **THEN** comprehension and location scores are recorded separately rather than treating the run as wholly correct

### Requirement: Complete efficiency accounting
Each run SHALL record elapsed time, model input/output/cache tokens, tool calls, exposed evidence volume, failures, and preprocessing/query costs, with cold, warm, and amortized ArticleGraph costs reported separately.

#### Scenario: Warm graph query is compared with raw reading
- **WHEN** aggregate efficiency is reported
- **THEN** the report distinguishes graph build cost from warm query cost and states the amortization assumption

### Requirement: Treatment-use validity gate
An ArticleGraph treatment run SHALL be invalid unless its direct tool trajectory and stored query receipts prove matching ArticleGraph operations occurred, and every scored run SHALL contain a parseable final answer.

#### Scenario: Infrastructure is exposed but unused
- **WHEN** a treatment agent has ArticleGraph instructions but produces no matching query receipt
- **THEN** the harness excludes the run from treatment-effect scoring and reports the validity failure

### Requirement: Evidence-backed conclusions
The benchmark SHALL NOT declare a winner unless paired runs pass validity gates and the report includes per-metric results, uncertainty, failures, and the underlying auditable run artifacts.

#### Scenario: Pilot agents exceed context and return no answer
- **WHEN** pilot runs consume tokens but fail to produce parseable final answers
- **THEN** the report labels the experiment invalid and uses it only as diagnostic evidence
