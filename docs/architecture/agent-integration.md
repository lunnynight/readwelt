# Host-neutral Agent integration

Readwelt does not require an internal model provider when an external Agent owns
the reading loop. The same versioned turn protocol is exposed through MCP,
HTTP, CLI, and the Python SDK. Claude Code and Codex are verified hosts, not
special implementations.

## Turn protocol

An Agent learns only three operations:

1. `start_agent_reading(source, ...)`
2. `get_agent_turn(run_id)`
3. `submit_agent_turn(run_id, candidate, agent_name, model, ...)`

The first two return `readwelt.agent-turn.v1`. While work remains:

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

The Agent generates only the `candidate` object described by
`request.response_schema`. Readwelt binds the run id, current stage, request
digest, Agent identity, and model before settlement. The response is the next
turn, so callers do not need a separate pull/status loop.

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

The run and mailbox are durable. A different Agent host can resume with
`get_agent_turn` as long as it can reach the same Readwelt project directory.

## MCP

Start the stdio server with an explicit project directory:

```powershell
uv run readwelt-mcp --project C:\path\to\project\.readwelt
```

`READWELT_PROJECT_ROOT` is the environment-variable equivalent. Every MCP host
uses the same command and the same three tools; no Claude- or Codex-specific
provider exists inside Readwelt.

Example MCP server entry:

```json
{
  "mcpServers": {
    "readwelt": {
      "command": "C:\\path\\to\\readwelt\\.venv\\Scripts\\readwelt-mcp.exe",
      "args": ["--project", "C:\\path\\to\\project\\.readwelt"]
    }
  }
}
```

## HTTP

The same loop is available to Agents that cannot host MCP:

```text
POST /v1/agent-sessions
GET  /v1/agent-sessions/{run_id}
POST /v1/agent-sessions/{run_id}/turns
```

The submit body contains:

```json
{
  "candidate": {"claims": [], "gaps": [], "warnings": []},
  "agent_name": "my-agent",
  "model": "my-model"
}
```

## CLI

Agents restricted to process execution can use:

```powershell
readwelt agent-start article.md --json
readwelt agent-turn run_... --json
readwelt agent-submit run_... candidate.json --agent-name my-agent --model my-model --json
```

Legacy `pull_stage_request` and `submit_stage_candidate` remain available for
existing clients, but new integrations should use the turn protocol.
