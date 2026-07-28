## ADDED Requirements

### Requirement: Skill-driven reading has no resident Readwelt process
The system SHALL provide a canonical Readwelt Skill that performs the external-Agent reading loop
only through short-lived `readwelt` CLI invocations and SHALL NOT require MCP, a daemon, or a
loopback service.

#### Scenario: Agent starts a reading
- **WHEN** an Agent invokes the Skill for an article and passes an explicit project directory
- **THEN** the Skill starts the run through the CLI, receives `readwelt.agent-turn.v1`, and the CLI process exits

#### Scenario: Agent resumes in another host
- **WHEN** a later Agent host supplies the same project directory and run id
- **THEN** `agent-turn` returns the durable current turn without relying on prior process memory

### Requirement: Skill remains a thin orchestration layer
The Skill SHALL use the request response schema supplied by Readwelt and SHALL NOT restate the
six-stage policies, ArticleGraph interpretation rules, completion criteria, or provider secrets.

#### Scenario: Stage candidate is generated
- **WHEN** the current turn requests a stage candidate
- **THEN** the Skill instructs the host Agent to satisfy `request.response_schema` and submits only that candidate

### Requirement: CLI supports complete machine-readable Agent operation
The CLI SHALL expose start, current-turn, stdin submission, diagnostics, and artifact retrieval
with versioned JSON results and structured non-zero failures.

#### Scenario: Candidate arrives through stdin
- **WHEN** `agent-submit` receives `-` as its candidate source and stdin contains one JSON object
- **THEN** the CLI validates and submits the object without creating a caller-managed temporary file

#### Scenario: Completed output is retrieved
- **WHEN** a completed turn includes an artifact digest
- **THEN** `artifact-get` returns bounded artifact metadata and a project-contained path in JSON

#### Scenario: Environment is checked
- **WHEN** an Agent runs `doctor --json` before a reading
- **THEN** the CLI reports its schema version, package version, normalized project directory, writability, and readiness without starting a provider

#### Scenario: Machine-readable failure
- **WHEN** a CLI request is invalid or the project mutation lock cannot be acquired
- **THEN** stdout remains free of non-JSON diagnostics, stderr contains a structured JSON error, and the process exits non-zero

### Requirement: MCP is absent from the distributed integration
The Readwelt distribution SHALL NOT declare an MCP dependency, executable, server module, Skill
dependency, or MCP installation instructions.

#### Scenario: Clean package installation
- **WHEN** Readwelt is installed with its normal or all optional dependencies
- **THEN** no MCP package is required and no `readwelt-mcp` executable is installed
