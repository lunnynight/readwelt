## ADDED Requirements

### Requirement: Mutating CLI operations are interprocess-safe
The system SHALL serialize mutable project operations across independent CLI processes using a
cross-platform project-local lock.

#### Scenario: Two processes mutate one project
- **WHEN** two CLI processes attempt project mutations at the same time
- **THEN** at most one process enters the mutable application operation and the other waits only up to the configured timeout

#### Scenario: Lock timeout
- **WHEN** the project lock remains held beyond the timeout
- **THEN** the waiting command exits non-zero with a stable `project_busy` error and does not mutate project state

#### Scenario: Process exits unexpectedly
- **WHEN** a lock-owning CLI process terminates
- **THEN** the operating system releases the lock and a later command can continue without a stale daemon or manual reaper

### Requirement: Read-only inspection remains concurrent
The system SHALL allow status, diagnostics, and artifact metadata inspection without acquiring the
project mutation lock.

#### Scenario: Inspect while another process mutates
- **WHEN** one CLI process holds the mutation lock and another requests read-only status
- **THEN** the read-only command does not wait for the mutation lock and never observes a partially written manifest

### Requirement: Persistence remains protocol-compatible
The locking and CLI migration SHALL NOT change stored run ids, stage order, request digests,
artifact digests, or the `readwelt.agent-turn.v1` schema.

#### Scenario: Resume a pre-migration run
- **WHEN** the CLI opens a valid run created before the migration
- **THEN** the current turn and subsequent settlement use the existing stored identities and schema
