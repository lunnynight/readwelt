---
name: readwelt
description: Use Readwelt for deep, traceable reading of articles, essays, papers, reports, EPUBs, and PDFs when the user wants the argument reconstructed, missing knowledge decompressed, the author model recovered, conclusions pressure-tested, or methods transferred. Drive the durable six-stage workflow through the short-lived Readwelt CLI. Do not use for ordinary summaries, unrelated question answering, or codebase context retrieval.
---

# Readwelt

Use the host Agent for reasoning and the `readwelt` CLI for source selection, stage order, bounded
evidence, validation, settlement, and persistence. Never start an MCP server, HTTP server, daemon,
or internal model provider for this workflow.

## Resolve the CLI and project

1. Prefer the installed `readwelt` executable.
2. In a Readwelt source checkout, fall back to `uv run readwelt`.
3. Choose one absolute project path and pass `--project <path>` on every command.
4. Run the provider-free preflight:

```text
readwelt doctor --project <absolute-project-path> --json
```

Stop if `ready` is false. Parse stdout as JSON. Treat non-zero exit status and the JSON error on
stderr as a failed operation.

## Start or resume

Start from a local source path:

```text
readwelt agent-start <source> --project <absolute-project-path> --json
```

Resume a known run:

```text
readwelt agent-turn <run-id> --project <absolute-project-path> --json
```

Keep the returned `run_id`. Runs are durable; do not rely on process or chat memory.

## Execute the turn loop

Inspect `action` in the `readwelt.agent-turn.v1` response:

- `generate_stage_candidate`: Use only the supplied `request`, evidence, and
  `request.response_schema`. Generate the candidate object required by that schema. Do not add the
  run, stage, provider, request digest, or transport envelope yourself.
- `completed`: Retrieve the requested final artifacts.
- `failed`: Report the structured warnings and stop.
- `inspect`: Call `agent-turn` once more only after checking the returned status; do not busy-loop.

Submit exactly one UTF-8 JSON candidate object through stdin:

```text
readwelt agent-submit <run-id> - --agent-name <host-name> --model <model-name> \
  --project <absolute-project-path> --json
```

Parse the returned next turn and continue until `completed`. If the turn contains
`validation_errors`, repair the candidate from those errors and the current response schema; never
bypass Readwelt validation.

The six-stage reading policy belongs to Readwelt. Do not restate or improvise stage definitions in
the Skill, and do not treat ArticleGraph locating signals as the final answer.

## Retrieve completion artifacts

Inspect metadata before loading content:

```text
readwelt artifact-get <sha256-digest> --project <absolute-project-path> --json
```

Load content only for the artifact needed in the response, normally `reader_report_markdown`:

```text
readwelt artifact-get <sha256-digest> --content \
  --project <absolute-project-path> --json
```

Do not inline every artifact or the full ArticleGraph into the Agent context.

## Operating rules

- Use `--json` for every machine call; do not scrape human-formatted output.
- Use `readwelt <command> --help` as the argument source of truth.
- Pass candidate JSON through stdin rather than shell command arguments or persistent temporary
  files.
- Keep authentication and model tokens in the Agent host. Do not write them into Readwelt state.
- On `project_busy`, wait briefly and retry the same idempotent operation; do not delete lock files.
- Preserve the returned run id, artifact digests, request schema, and provenance identities exactly.
