## Context

Readwelt currently exposes one application service through CLI, HTTP, Python, and stdio MCP
adapters. The MCP adapter contains no unique reading capability, but every Agent host owns its
stdio server lifetime. On Windows, a host or descendant process can remain alive across chats and
retain an entire Readwelt dependency graph in memory.

The existing CLI already exposes `agent-start`, `agent-turn`, and `agent-submit` over the durable
`readwelt.agent-turn.v1` protocol. The missing pieces are final artifact access, stdin submission,
diagnostics, a distributable Skill, and explicit interprocess coordination.

`knowsuchagency/mcp2cli` was inspected at revision `dd2a5a6`. Its MCP modes still connect to or
spawn an MCP server, and its optional sessions deliberately create a daemon, so it is not an
acceptable Readwelt runtime dependency. Its strict JSON output, stdin body, CLI-help discovery,
and concise Skill/CLI separation are adopted as interface patterns only.

## Goals / Non-Goals

**Goals:**

- Make Skill-driven, short-lived CLI execution the canonical Agent integration.
- Complete all six stages without a resident Readwelt server process.
- Preserve durable resume across chats, hosts, and Agent implementations.
- Prevent concurrent CLI mutations from corrupting or losing project state.
- Remove MCP packaging and documentation completely.

**Non-Goals:**

- Moving six-stage policy, Completion Engine policy, or ArticleGraph interpretation into the
  Skill.
- Replacing the application service, Python SDK, or optional HTTP adapter.
- Dynamically generating Readwelt commands from MCP tool schemas.
- Adding a background daemon, process reaper, Job Object, or reference-counted server.

## Decisions

### Use a canonical repository Skill over a generated MCP wrapper

The repository will ship `skills/readwelt/SKILL.md` and Codex UI metadata. The Skill contains
trigger guidance and the four-operation loop (start, inspect, submit, retrieve), while CLI help and
versioned JSON schemas remain the argument and payload source of truth.

Alternative: generate a Skill by introspecting the MCP server with mcp2cli. Rejected because the
generated wrapper would continue to spawn an MCP subprocess and expose transport concepts that are
not part of Readwelt's product.

### Keep the existing turn protocol and extend CLI parity

The canonical commands remain `agent-start`, `agent-turn`, and `agent-submit`. `agent-submit`
accepts `-` to read one JSON object from stdin. `artifact-get` retrieves the completion artifacts,
and `doctor` performs a no-provider environment check. Every machine path supports `--json`, with
valid JSON only on stdout and structured errors on stderr.

Alternative: rename all commands into a new nested command tree. Rejected because it adds
migration cost without improving the protocol or process lifetime.

### Serialize mutable project operations with a mature file-lock library

CLI mutations acquire a project-local interprocess lock for the duration of one application
operation. Model reasoning happens outside the lock, so the conservative project scope does not
hold a lock while an Agent thinks. A mature cross-platform lock package is used rather than a
hand-written Windows lock.

The initial lock is intentionally project-scoped. CAS reads and read-only status/artifact commands
remain concurrent. Later measurement may split this into per-run and index locks without changing
the CLI contract.

Alternative: rely only on atomic `os.replace`. Rejected because atomic replacement prevents
partial files but does not make read-modify-write sequences mutually exclusive.

### Remove MCP rather than deprecating it in place

The package drops the `mcp` extra, `readwelt-mcp` executable, implementation module, tests, and
installation documentation in the same breaking change. Keeping an optional adapter would preserve
the exact accidental process topology this change is meant to eliminate.

## Risks / Trade-offs

- **Existing MCP configurations fail after upgrade** → Return a clear migration note in release
  documentation and provide equivalent Skill/CLI commands.
- **Project-wide locking reduces write concurrency** → Keep locks limited to short deterministic
  operations and add timeout/busy errors; Agent inference never runs under the lock.
- **A Skill may duplicate product policy** → Test that the Skill only follows the response schema
  supplied by Readwelt and references CLI help instead of embedding stage schemas.
- **Artifact output can exceed Agent context** → `artifact-get` defaults to metadata/path JSON;
  content is emitted only when explicitly requested.
- **CLI invocation from different working directories selects different projects** → Require the
  Skill to pass an explicit normalized `--project` path on every command.

## Migration Plan

1. Add CLI parity, strict tests, and interprocess locking while MCP still exists.
2. Add and forward-test the canonical Readwelt Skill against the CLI.
3. Remove MCP packaging, code, tests, and documentation.
4. Run clean-install CLI end-to-end tests, full Python/Rust checks, OpenSpec strict validation, and
   Code Intel/Sentrux gates.
5. Rollback, if required, by reverting the change as one unit; no persisted run schema is changed.

## Open Questions

None block implementation. Lock granularity can be refined later from measured contention without
changing the public protocol.
