# D1 non-scored pilot corrections

These attempts are excluded from scoring. Corrections were frozen before any scored D1 run.

## Attempt 1: outer timeout and duplicate process tree

- Result roots: `pilot-20260729T071413Z`, `pilot-20260729T071436Z`.
- Finding: the outer 10-second command timeout detached child benchmark processes.
- Correction: the runner now owns a per-condition process group, applies the same wall timeout to both conditions, and terminates the exact process tree on timeout.

## Attempt 2: launcher argument re-parsing

- Result root: `pilot-20260729T072407Z`.
- Finding: passing the multiline prompt as a `.cmd` argument caused the launcher to return plain text instead of the requested event stream; baseline took 292.8 seconds and treatment timed out at 300 seconds.
- Correction: keep the absolute official `claude.cmd` launcher, send the prompt over stdin, keep only control flags on the command line, and disable unrelated plugins and MCP servers symmetrically.

## Attempt 3: real trajectory but invalid matched pair

- Result root: `pilot-20260729T074317Z`.
- Finding: event and usage telemetry worked. Baseline made a forbidden dependency-install attempt. Treatment made direct ArticleGraph queries, but default query output reached 902.2 KB, receipts lived in persisted tool output, and the agent exhausted 16 turns before producing a structured answer.
- Correction: point baseline at the existing repository virtual environment and forbid installs; bound every treatment query to 5 hits, 4,000 evidence characters, and 1,200 estimated tokens; cap treatment at three `search` calls; normalize raw and persisted tool output into immutable receipt artifacts; reject mutating tool commands and resolved-model mismatches.

## Attempt 4: continuation escaped the response budget

- Result root: `pilot-20260729T080322Z`.
- Finding: five hits used only 67 estimated evidence tokens, but the response serialized the entire remaining candidate frontier into a 794,514-character continuation. The 803 KB tool result forced repeated persisted-output inspection and exhausted 16 turns.
- Correction: continuation now carries only immutable request/snapshot digests, next offset, and the last ordering key; the service deterministically rebuilds and verifies candidate order. A real-corpus replay reduced the same bounded response to 9,638 bytes and the continuation to 912 characters.

No metric result from these attempts was used to choose documents, gold anchors, release thresholds, or scoring rules.
