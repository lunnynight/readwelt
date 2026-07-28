## 1. CLI Safety Foundation

- [x] 1.1 Add a mature cross-platform file-lock dependency and a project mutation lock abstraction.
- [x] 1.2 Apply bounded project locking to mutating CLI commands with a stable `project_busy` error.
- [x] 1.3 Add concurrency and lock-release regression tests using independent processes.

## 2. Agent CLI Completion

- [x] 2.1 Support `agent-submit RUN_ID -` with one JSON object read from stdin.
- [x] 2.2 Add `artifact-get DIGEST` with project-contained metadata and optional explicit content.
- [x] 2.3 Add provider-free `doctor --json` diagnostics and stable schema/version fields.
- [x] 2.4 Add subprocess end-to-end tests for start, resume, submit, completion artifact retrieval, JSON-only output, and process exit.

## 3. Readwelt Skill

- [x] 3.1 Initialize the canonical `skills/readwelt` package with Codex interface metadata.
- [x] 3.2 Implement the thin Skill workflow using explicit project paths, CLI help, stdin submission, bounded artifacts, and the supplied response schema.
- [x] 3.3 Validate the Skill package and exercise it against a real CLI Agent turn without MCP.

## 4. Remove MCP Distribution

- [x] 4.1 Remove the MCP dependency groups, `readwelt-mcp` script, server module, and MCP-specific tests.
- [x] 4.2 Update README and Agent integration documentation to make Skill + CLI canonical and document the breaking migration.
- [x] 4.3 Regenerate the lockfile and verify a clean package exposes no MCP dependency or executable.

## 5. Acceptance

- [x] 5.1 Run OpenSpec strict validation and all Python and Rust CI-equivalent checks.
- [x] 5.2 Run Code Intel Pipeline and Sentrux gates, repairing structural regressions without weakening baselines.
- [x] 5.3 Record mcp2cli provenance, adopted patterns, rejected runtime behavior, and final acceptance evidence.
