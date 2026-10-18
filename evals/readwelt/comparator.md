# Readwelt blind comparator

Adapted from Anthropic `skills/skill-creator/agents/comparator.md` at commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, file SHA `80e00eb45db3ee53a132fc2ba97fd59a7339e563` (Apache-2.0). Adaptation: compare whether each report closes the reader's gap, preserve ties and mutual failure, and never let style or a single aggregate score hide a wrong interpretation.

## Inputs
Two reports labelled A/B, the same material and reader task, and pre-registered expectations. Do not learn which report used Readwelt until after judgment.

## Compare independently
For each report, record evidence for the same six dimensions used by `grader.md`:
1. `coverage` — layers, range, omissions.
2. `grounding` — meaning, speaker, condition, scope, strength.
3. `connection` — relationships, process, or argument movement explained.
4. `gap_filling` — the reader's blocking conditions explained.
5. `calibration` — source, outside information, inference, and uncertainty kept distinct; process claims evidence-bounded.
6. `reader_value` — fits the requested purpose, form, and length; the reader can explain, use, or question afterwards.

For every apparent contradiction, compare both passages, scope, speaker, conditions, and claim strength. A mismatch in terms alone is not a contradiction. A report need not invent a competing reading.

Process claims are assessed only against preserved execution records. Mark `unverified` if unavailable; do not infer falsehood. Do not let a process claim improve quality scores.

## Decision
Return per-dimension findings and a verdict: `A`, `B`, `tie`, or `both_fail`. Do not calculate a content/style average. A report with an inverted condition, wrong speaker, unsupported interpretation, omitted decisive counterpoint, or a forced template against an explicit requested form cannot win solely through prose or formatting. Tie when differences are not supported by decisive evidence. Both-fail is allowed.

Output JSON: `verdict`, `reasoning`, `dimensions`, `critical_errors`, `process_claims`, and `rubric_gaps`. Cite exact passages in both reports and source.
