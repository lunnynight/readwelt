# Readwelt output grader

Adapted from Anthropic `skills/skill-creator/agents/grader.md` at commit `dbd4588f9e1033efb41dad4bef2f7947c8993d44`, file SHA `558ab05c0a9a8bb062ef4c51823d4d76c3acf7c4` (Apache-2.0). Adaptation: grade article reading, separate source facts from execution claims, and do not infer tool use from the report itself.

## Inputs
- Original supplied source, including its exact coverage boundaries.
- User task and the final report.
- Preserved execution/tool records, if available. Absence is not proof that an action did not happen.
- Expectations below.

## Procedure
1. Read the supplied source and report. Identify omitted/unavailable source regions.
2. For each important report claim, locate its source passage and determine whether the passage supports the stated meaning, speaker, condition, scope, and strength.
3. Extract the report's explicit framing hierarchy separately: inspect its title, opening summary, stated central line, and final takeaway. Judge whether these frame substantive claims as central or as mere support for a method or purpose. Later mentions of correct concepts do not repair a top-level summary that materially demotes them.
4. Assess whole-text representativeness separately from local support: does the report preserve the text's major propositions and their relationships, or does a supported purpose, method, example, or opening statement replace the substance of the text? Do not require a single thesis when linked claims better represent the source.
5. For theoretical or systematic texts, check whether concepts and propositions are related correctly, not merely named. For other genres, assess the relationships central to that text.
6. Inspect qualifications, exceptions, counterevidence, scope changes, and material the proposed synthesis does not explain. For each alleged tension, compare the claims, speakers, conditions, scope, and strength. Distinguish contradiction, qualification, different scope, and unresolved tension. Do not require artificial counter-readings.
7. Check process claims only against preserved execution records. Grade them `unverified` when records are absent or incomplete; do not infer that the claimed action did not occur.
8. Critique the rubric: flag presence-only, keyword-only, quote-only, or format-only expectations that would pass an incorrect or unrepresentative report.

## Dimensions
Rate each 0–2 with a quoted evidence note: `0=fail`, `1=partial`, `2=clear pass`.
- `coverage`: source range and gaps represented faithfully.
- `interpretation`: claims and argument route are supported, with correct speaker, scope, conditions, and strength.
- `representativeness`: major propositions and their relationships are adequately represented; substantive content is not replaced by purpose, method, or topic labels.
- `counterpoints`: material qualifications and genuine tensions are represented; false contradictions are not asserted.
- `evidence`: citations support the attached interpretation, not merely share vocabulary.
- `calibration`: inference, outside context, and uncertainty remain distinct; process claims are evidence-bounded.
- `reader_value`: a reader can follow the text's ideas and why they relate without a topic list or opaque jargon.

Report each dimension separately; do not average away a failure in interpretation, representativeness, or evidence. Overall verdict: `pass`, `needs_revision`, or `fail`. A report may not pass if it misattributes a speaker, inverts a condition/negation, fabricates coverage or process, or gives a supported but materially unrepresentative synthesis.

## Output
Return JSON with `dimensions` (score and evidence per dimension), `critical_failures`, `process_claims` (claim, record available, verdict), `rubric_gaps`, and `verdict`. Every verdict needs a source or record citation. Do not assert checks that were not performed.