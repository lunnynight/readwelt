## ADDED Requirements

### Requirement: Representative document corpus
The acceptance corpus SHALL include Chinese and English TXT, HTML, native PDF, scanned PDF, and EPUB documents; argument, exposition, and narrative structures; repeated passages; quotations; tables; figures; captions; numbers; missing pages or structure; and at least one document over 100,000 Chinese characters or equivalent tokens.

#### Scenario: Corpus validation
- **WHEN** the long-document benchmark starts
- **THEN** it fails early if required formats, structural cases, languages, or length classes are absent

### Requirement: Source reachability acceptance
Every benchmark document MUST achieve complete normalized-range reachability and complete preservation of all backend-exposed source elements. Unsupported higher-level semantics or geometry MAY be reported as capability gaps but MUST NOT reduce raw source reachability.

#### Scenario: One unreachable range
- **WHEN** any normalized source range cannot resolve to a source record
- **THEN** the benchmark fails source completeness for that document

### Requirement: Bounded traversal acceptance
For documents larger than the configured provider budget, the benchmark SHALL prove that deterministic continuation can visit the entire Source Plane with every packet within the hard serialized-input budget and without mandatory full-text injection.

#### Scenario: Traverse a 100,000-character document
- **WHEN** the benchmark follows continuation cursors until exhaustion
- **THEN** all eligible source identities are visited, no cursor loop or silent omission occurs, and every packet respects the hard budget

### Requirement: Navigation quality metrics
The benchmark SHALL report must-hit Recall at token budget, critical-anchor miss rate, source and view coverage, input tokens, full-text fallback rate, traversal page count, p50/p95 latency, peak memory, backend failures, and unresolved projection counts.

#### Scenario: Benchmark report generated
- **WHEN** a benchmark run completes
- **THEN** its report contains all required metrics by format, language, length class, and backend configuration

### Requirement: Long-document artifact volume and deduplication
The benchmark SHALL report per-artifact bytes, naive embedded bytes, content-addressed unique bytes, deduplication ratio, build peak memory, and bounded read behavior for the 100,000+ character corpus. Aggregate build artifacts MUST reference child artifacts rather than re-embedding them, and large Source Plane, SourceIndex, and ledger artifacts MUST support bounded or streaming reads.

#### Scenario: Build the 100,000-character document twice
- **WHEN** the same source revision and build policy are rebuilt
- **THEN** immutable child artifacts reuse content identities, aggregate artifacts remain reference-only, duplicate stored bytes do not grow, and reading one bounded page does not require materializing every large child artifact

### Requirement: Comparative retrieval baselines
The benchmark SHALL compare full-text where it fits, lexical retrieval, dense retrieval where enabled, hybrid retrieval, reranking where enabled, and hybrid plus source-coverage rescue. It MUST NOT declare a fixed token-saving target without measured corpus evidence.

#### Scenario: Retrieval strategy comparison
- **WHEN** two navigation strategies are evaluated
- **THEN** the report compares recall, critical misses, tokens, latency, resource use, and fallback rate under the same corpus and budget

### Requirement: Regression and architecture gates
Acceptance SHALL include focused unit/integration tests, existing regression tests, strict OpenSpec validation, and Sentrux rules plus scoped/root structural comparison. Pre-existing root baseline degradation MUST be reported separately from change-introduced degradation.

#### Scenario: Root Sentrux baseline already degraded
- **WHEN** the root gate is below its recorded baseline before implementation
- **THEN** acceptance records the initial state, requires no new scoped degradation, and does not falsely claim the pre-existing issue was fixed
