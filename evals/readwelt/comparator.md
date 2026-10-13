# Readwelt blind comparator

Adapted from Anthropic `skills/skill-creator/agents/comparator.md` at commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, file SHA `80e00eb45db3ee53a132fc2ba97fd59a7339e563` (Apache-2.0). Adaptation: compare reading quality, preserve ties and mutual failure; do not use style or a single aggregate score to hide wrong interpretations.

## Inputs
Two or more reports labelled with neutral identifiers, the same source, prompt, and pre-registered expectations. Hide system/Skill identity until judgments are complete. For three-way comparisons, assess every report individually before pairwise preference.

## Compare independently
For each report, record evidence for:
1. subject and substantive propositions;
2. relationships among major propositions and the argument route;
3. distinction among substantive content, method, and purpose;
4. whole-text representativeness, coverage, qualifications, scope changes, and unresolved tensions;
5. source support, speaker/negation/condition accuracy, uncertainty;
6. reader-facing clarity;
7. explicit framing hierarchy: quote the title, opening summary, stated central line, and final takeaway. Judge whether these place substantive claims at the center or demote them beneath purpose/method. Later term mentions do not repair an unrepresentative top-level framing.

A supported claim is not automatically representative of the whole. In particular, do not let a stated purpose, method, opening frame, or closing takeaway substitute for the text's substantive claims. A list of correct topics without explaining their relations is incomplete. Do not require one central sentence when linked claims better represent the source.

For every apparent contradiction, compare both source passages, scope, speaker, conditions, and claim strength. A mismatch in terms alone is not a contradiction. A report need not invent a competing reading.

Process claims are assessed only against preserved execution records. Mark `unverified` if unavailable; do not infer falsehood. Do not let a process claim improve quality scores.

## Decision and output
Do not calculate a content/style average. A report with an inverted condition, wrong speaker, unsupported or materially unrepresentative synthesis, or omitted decisive proposition cannot win solely through prose or formatting. A report may be inadequate even when another report is worse. Tie when differences are not supported by decisive evidence.

Return JSON in this shape:

```json
{
  "individual_assessments": {
    "A": {"verdict": "pass | needs_revision | fail", "findings": []},
    "B": {"verdict": "pass | needs_revision | fail", "findings": []}
  },
  "pairwise_preferences": {
    "A_vs_B": "A | B | tie | both_fail"
  },
  "overall": "A | B | tie | both_fail | inconclusive",
  "critical_errors": [],
  "process_claims": [],
  "rubric_gaps": []
}
```

Include one `individual_assessments` entry per report and every unordered pair in `pairwise_preferences`. `overall` names a winner only when it is adequately supported; use `both_fail` when all reports fail and `inconclusive` when no overall ordering is justified. Cite exact passages in each report and the source.