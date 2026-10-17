# Host-neutral Skill and CLI integration

Readwelt is a local tool, not a resident Agent server. An external Agent owns generation while
short-lived CLI processes load durable project state, return one actionable turn, settle one
candidate, and exit. The canonical integration is the repository Skill at
`skills/readwelt/SKILL.md`.

The optional HTTP and Python interfaces remain application adapters, but the Skill requires
neither. The former stdio MCP adapter and `readwelt-mcp` executable were removed because every
host/subagent created another long-lived Python process tree without adding reading capability.

Claude Code also has an optional direct provider implementation. It launches one official CLI
subprocess per bounded operation, reuses host authentication without persisting credentials, and
is separate from the Skill-owned Agent loop.

## Process and state model

```text
Codex / Claude Code / Gemini
             |
       skills/readwelt
             |
    short-lived readwelt CLI
             |
   .readwelt durable project
             |
 ReadweltApplicationService
```

Each command receives an explicit absolute `--project` path. Runs, requests, submitted candidates,
settled stages, provenance, and completion artifacts survive process and chat termination. A later
host can resume from the same project directory and run id.

Mutable CLI operations acquire a bounded project-local interprocess lock. The lock covers only one
deterministic application operation; Agent inference occurs after the CLI exits and therefore
never holds the lock. Status, diagnostics, and artifact inspection remain read-only.

## Turn protocol

The Agent-facing operations are:

1. `agent-start SOURCE`
2. `agent-turn RUN_ID`
3. `agent-submit RUN_ID -`
4. `artifact-get DIGEST`

`agent-start` and `agent-turn` return `readwelt.agent-turn.v1`. While work remains:

```json
{
  "schema_version": "readwelt.agent-turn.v1",
  "run_id": "run_...",
  "action": "generate_stage_candidate",
  "stage": "stage_1_mainline",
  "request": {
    "evidence_packet": {},
    "response_schema": {},
    "provenance": {"request_digest": "sha256:..."}
  }
}
```

The host generates only the candidate object described by `request.response_schema`. Readwelt
binds the run id, current stage, request digest, Agent identity, and model during submission:

Stage 3 also requires `decompression_units` in the current response schema. Each unit explains a
decompression point and links it to claim ids and admitted source citations; optional fields capture
introduced or assumed concepts, mechanism steps, dependencies, missing prerequisites, tacit
practices, assumptions, inferred relations, boundaries, alternatives, changed-condition examples,
and uncertainties. Readwelt persists these units inside the stage artifact as
`decompression-artifact.v1`. Hosts must use the stage-specific schema returned in each request.

```powershell
Get-Content .\candidate.json -Raw |
  readwelt agent-submit run_... - --agent-name codex --model host-model `
    --project C:\reading\.readwelt --json
```

The result is the next turn. No pull/status busy loop and no in-memory session identity are
required.

After stage 6:

```json
{
  "schema_version": "readwelt.agent-turn.v1",
  "run_id": "run_...",
  "action": "completed",
  "outputs": [
    {"artifact_type": "reading_bundle", "content_digest": "sha256:..."},
    {"artifact_type": "reader_report_markdown", "content_digest": "sha256:..."}
  ]
}
```

Inspect artifact metadata before loading content:

```powershell
readwelt artifact-get sha256:... --project C:\reading\.readwelt --json
readwelt artifact-get sha256:... --content --project C:\reading\.readwelt --json
```

## Skill boundary

The Skill decides whether a user request needs Readwelt and orchestrates the CLI loop. It does not
contain stage policy, ArticleGraph interpretation rules, Completion Engine policy, response
schemas, credentials, or model routing. Those remain versioned Readwelt inputs and contracts.

The host must:

- pass the same normalized project path on every invocation;
- use `--json` and parse stdout rather than scraping human output;
- build the candidate from the current `request.response_schema`;
- submit candidate JSON through stdin;
- preserve run ids, digests, and provenance identities exactly;
- retrieve only the completion artifacts needed for the user response.

## ArticleGraph provider boundary

Readwelt, rather than the Agent host, decides what the current stage may read. The provider-bound
`StageRequest` contains a bounded StageView envelope with:

- source excerpts and typed identities for the text units/slices and advisory graph objects
  actually presented;
- SourceIndex, graph, and provenance-ledger lineage;
- separate source, visited, selected, serialized, presented, cited, critical, and omitted coverage
  state;
- explicit blocking records and integrity-bound continuation when the source does not fit the hard
  serialized-input budget.

Provider-visible material is validated through SourceIndex and append-only ledger events to typed
Source Plane records. Unknown or stale references fail empty. The Agent may cite admitted source
and ArticleGraph identities, but its output remains a stage conclusion and cannot reclassify
itself as a source fact.

ArticleGraph is a locating substrate, not the Agent's answer. Xberg supplies primary content
extraction, while the Source Plane retains the original file, exact normalized ranges, preserved
elements, and capability gaps. An image-only scanned PDF remains addressable even when OCR text is
absent.

The host executes candidate generation. Readwelt owns stage order, budget, continuation,
validation, settlement, and persistence. `CompletionPlan` and the Completion Engine remain product
capabilities rather than Skill prompt content.

## Migration from MCP

Remove any `readwelt` entry from host `mcpServers` configuration. Install the repository Skill and
ensure the `readwelt` executable is available instead. There is no replacement daemon, port,
stdio transport, Job Object, parent watcher, or process reaper.
