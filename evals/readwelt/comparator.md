# Readwelt blind comparator

Adapted from Anthropic `skills/skill-creator/agents/comparator.md` at commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, file SHA `80e00eb45db3ee53a132fc2ba97fd59a7339e563` (Apache-2.0). Adaptation: compare reading quality, preserve ties and mutual failure; do not use style or a single aggregate score to hide wrong interpretations.

## Inputs
Two reports labelled A/B, the same source, task prompt, and pre-registered expectations. Do not learn which report used Readwelt until after judgment.

## Compare independently
For each report, record evidence for:
1. central claim/pivot or justified parallel lines;
2. argument route and example functions;
3. coverage, material qualifications, scope changes, and unresolved tensions;
4. source support, speaker/negation/condition accuracy, uncertainty;
5. reader-facing clarity.

For every apparent contradiction, compare both source passages, scope, speaker, conditions, and claim strength. A mismatch in terms alone is not a contradiction. A report need not invent a competing reading.

Process claims are assessed only against preserved execution records. Mark `unverified` if unavailable; do not infer falsehood. Do not let a process claim improve quality scores.

## Decision
Return per-dimension findings and a verdict: `A`, `B`, `tie`, or `both_fail`. Do not calculate a content/style average. A report with an inverted condition, wrong speaker, unsupported central interpretation, or omitted decisive counterpoint cannot win solely through prose or formatting. Tie when differences are not supported by decisive evidence. Both-fail is allowed.

Output JSON: `verdict`, `reasoning`, `dimensions`, `critical_errors`, `process_claims`, and `rubric_gaps`. Cite exact passages in both reports and source.