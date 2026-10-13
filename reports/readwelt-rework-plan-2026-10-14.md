# Readwelt system rework plan

Baseline: `ca3ac081` (user-specified). Primary deliverable remains a pure reading Skill; CLI is optional.

## Sequence
1. Preserve current skill/scorer behavior as baseline and add failing semantic cases for false contradiction, genuine tension, inverted condition, speaker attribution, partial source, and unsupported process claims.
2. Adjust `SKILL.md` so the provisional controlling claim cannot erase important qualifications, contradictions, scope changes, or unaccounted passages; test internal relationships before external context. Competing interpretations remain optional unless genuinely supported.
3. Improve deterministic scoring only for mechanically decidable properties (valid schema, exact source quote/reference); move semantic understanding to a rubric that judges answer relevance, scope, speaker, evidence entailment, tensions, and calibrated uncertainty. Keep score dimensions separate; no quote-only comprehension credit.
4. Adapt grader/comparator structures from pinned upstream sources, preserving provenance/licensing notices; do not copy domain-specific scientific criteria or averaging/tie rules.
5. Add minimal optional quote checker, update OpenAI metadata/README to make pure Skill the default, document CLI/tool limitations.
6. Run the regression cases and existing focused suites; compare baseline and revised reports using blinded identities and record costs, scores, and failures.

## Acceptance
- Genuine tension case must identify two relevant source passages, explain their scope, and assess plausible reconciliation; two quotations or “dialectical tension” alone fail.
- No forced counter-reading when only one reading is supported.
- Inverted conditions, author/opponent confusion, irrelevant answers with keywords, and quote-only answers fail semantic grading.
- Partial source cannot be represented as full coverage; process claims without preserved evidence are marked unverified, not assumed false.
- Position and literal quote checks are deterministic and cannot independently award comprehension.
- Pure Skill use needs no CLI/runtime; optional tool limits are explicit.
- Do not claim hard prevention of process statements in pure Skill mode.
