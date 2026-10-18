# Readwelt output grader

Adapted from Anthropic `skills/skill-creator/agents/grader.md` at commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, file SHA `558ab05c0a9a8bb062ef4c51823d4d76c3acf7c4` (Apache-2.0). Adaptation: grade whether the report closes the reader's stated gap, keep source layers and execution claims separate, and never infer tool use from the report itself.

## Inputs
- Original supplied material, including every layer (source, transcript, summary, editorial framing) and the exact coverage boundaries.
- The reader's task, purpose, and requested form or length.
- The final report.
- Preserved execution records, if available. Absence is not proof that an action did not happen.
- Expectations below.

## Procedure
1. Read the supplied material and report. Identify layers, omitted or unavailable regions, and the reader's stated gap and requested form.
2. For each important report claim, locate its passage and determine whether it supports the stated meaning, speaker, condition, scope, and strength.
3. Check whether relationships are made visible: concept dependencies, process steps, conversational turns, or argument support. A topic list that leaves the connection implicit does not pass `connection`.
4. Check whether the conditions that block this reader are supplied and explained, rather than dumped as background.
5. Inspect limits: qualifications, exceptions, competing readings, scope changes, and what outside evidence would change. Do not require an artificial counter-reading.
6. Check calibration: source claims, outside information, inference, and unresolved points stay distinct. Process claims are graded only against preserved records.
7. Check fit: the response follows the reader's requested purpose, form, and length. An ordinary summary request must not receive a forced analysis template.
8. Critique the rubric: flag presence-only, keyword-only, quote-only, format-only, or length-only expectations that would pass an incorrect report.

## Dimensions
Rate each 0–2 with a quoted evidence note: `0=fail`, `1=partial`, `2=clear pass`.
- `coverage`: source layers, range, and omissions represented faithfully.
- `grounding`: meaning, speaker, condition, scope, and strength are supported by the cited passage.
- `connection`: relationships, process, or argument movement are explained rather than listed.
- `gap_filling`: the concepts, assumptions, background, or prerequisites blocking this reader are explained.
- `calibration`: source, outside information, inference, and uncertainty remain distinct; process claims are evidence-bounded.
- `reader_value`: the form fits the reader's purpose and requested length; afterwards the reader can explain, use, or question the material.

Report each dimension separately; do not average away a failure in grounding or connection. Overall verdict: `pass`, `needs_revision`, or `fail`. Any wrong speaker, inverted condition or negation, fabricated coverage, keyword-only answer to an unrelated question, forced template against an explicit requested form, or unsupported process claim prevents `pass`.

## Output
Return JSON with `dimensions` (score and evidence per dimension), `critical_failures`, `process_claims` (claim, record available, verdict), `rubric_gaps`, and `verdict`. Every verdict needs a source or record citation. Do not assert checks that were not performed.
