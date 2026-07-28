## Why

Readwelt is a local reading tool whose durable state already lives in the project directory, but
its stdio MCP adapter causes every Agent host and subagent to keep another Python process tree
alive. Closing a chat does not reliably close the host process, so the adapter consumes memory
without adding product capability that is not already available through the CLI.

## What Changes

- **BREAKING** Remove the `readwelt-mcp` executable, MCP Python dependency, stdio server, and MCP
  installation contract.
- Make a short-lived, machine-readable CLI the canonical external-Agent interface.
- Add stdin candidate submission, artifact retrieval, and environment diagnostics required for a
  complete six-stage Skill workflow.
- Ship a host-neutral Readwelt Skill that decides when to use Readwelt and drives the versioned
  `readwelt.agent-turn.v1` protocol without duplicating six-stage product policy.
- Add cross-process locking around mutable run and mailbox state so separate CLI invocations and
  Agent sessions cannot silently overwrite each other.
- Preserve the Python application service and optional HTTP adapter as subordinate interfaces;
  neither is required by the Skill workflow.
- Adopt the useful CLI patterns observed in `knowsuchagency/mcp2cli` at revision `dd2a5a6`
  (strict JSON, stdin request bodies, concise Skill instructions) without retaining an MCP
  transport or daemon.

## Capabilities

### New Capabilities

- `skill-cli-agent-integration`: A discoverable Readwelt Skill can run and resume the complete
  six-stage Agent loop through short-lived CLI processes and retrieve final artifacts.
- `cli-project-safety`: Concurrent CLI processes serialize mutations per run while preserving
  durable recovery, idempotency, and deterministic machine-readable failures.

### Modified Capabilities

None. The existing ArticleGraph and six-stage contracts remain unchanged.

## Impact

- Packaging: `pyproject.toml`, lockfile, distribution metadata, and optional dependencies.
- Interfaces: `src/readwelt/cli`, removal of `src/readwelt/mcp`, CLI and facade tests.
- Persistence: run manifests, external-Agent mailbox, and project-scoped locks.
- Agent distribution: a canonical repository Skill with validated metadata.
- Documentation: README and host-neutral Agent integration guidance.
