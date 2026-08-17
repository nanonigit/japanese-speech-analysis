# Task Plan: Objective lexical Range module

## Goal

Add a deterministic lexical Range module that turns Fluency's hiragana transcript into objective vocabulary evidence for the CEFR/JFS speech-evaluation pipeline.

## Current Phase

Phase 3 — API and Judge evidence integration

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

- [ ] Attach Range data to objective data and Judge input.
- [ ] Update prompt contract and API tests.
- [ ] Run focused tests and commit the green integration.
- **Status:** in_progress

### Phase 4: Verification and UML

- [ ] Run the full automated suite and coverage check if available.
- [ ] Review the diff and generate a code-derived UML sequence diagram.
- [ ] Compare the UML with the agreed target diagram.
- **Status:** pending

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
