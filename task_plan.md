# Task Plan: Objective lexical Range module

## Goal

Add a deterministic lexical Range module that turns Fluency's hiragana transcript into objective vocabulary evidence for the CEFR/JFS speech-evaluation pipeline.

## Current Phase

Complete

## Phases

### Phase 1: Requirements and test design

- [x] Confirm current API and Fluency handoff.
- [x] Record accepted scope and exclusions.
- [x] Add failing Range unit tests and validate RED.
- **Status:** complete

### Phase 2: Range core

- [x] Implement deterministic token, lookup, and aggregate logic.
- [x] Run focused tests and commit the green core.
- **Status:** complete

### Phase 3: API and Judge evidence integration

- [x] Attach Range data to objective data and Judge input.
- [x] Update prompt contract and API tests.
- [x] Run focused tests and commit the green integration.
- **Status:** complete

### Phase 4: Verification and UML

- [x] Run the full automated suite and coverage check.
- [x] Review the diff and generate a code-derived UML sequence diagram.
- [x] Compare the UML with the agreed target diagram.
- **Status:** complete

### Phase 5: Console evidence presentation

- [x] Show distinct Fluency and Range processing stages in the interactive console.
- [x] Print separate Fluency and Range objective-evidence sections.
- [x] Remove the interactive human CEFR-level selection prompt.
- [x] Verify the revised console flow with focused and full automated tests.
- **Status:** complete

### Phase 6: Runtime dependency repair

- [x] Reproduce the console failure with the launcher Python interpreter.
- [x] Add a launcher-environment regression test for the default Range extractor.
- [x] Synchronize the locked dependencies and `.venv` with the Range requirements.
- [x] Verify the console smoke path without a live Judge.
- **Status:** complete

## Decisions Made

| Decision | Rationale |
|---|---|
| Range is lexical-only in this release | Grammar range and paraphrase cannot be objectively derived from the current hiragana transcript. |
| Range returns data; API service owns integration | Keeps module boundaries explicit and avoids mutating service-owned payloads. |
| JLPT data is evidence, not a CEFR verdict | CEFR/JFS assessment is task and performance based. |
| No runtime dictionary download | Ensures deterministic, offline analysis. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `uv` command not found | 1 | Use the repository virtual environment directly; this is not a valid RED result. |
| `coverage` module not found | 1 | Install the test-only coverage tool, then run the full suite under coverage. |
