# Task Plan: Objective lexical Range module

## Goal

Add a deterministic lexical Range module that turns Fluency's hiragana transcript into objective vocabulary evidence for the CEFR/JFS speech-evaluation pipeline.

## Current Phase

Phase 1 — requirements and test design

## Phases

### Phase 1: Requirements and test design

- [x] Confirm current API and Fluency handoff.
- [x] Record accepted scope and exclusions.
- [ ] Add failing Range unit and API integration tests.
- **Status:** in_progress

### Phase 2: Range core

- [ ] Implement deterministic token, lookup, and aggregate logic.
- [ ] Run focused tests and commit the green core.
- **Status:** pending

### Phase 3: API and Judge evidence integration

- [ ] Attach Range data to objective data and Judge input.
- [ ] Update prompt contract and API tests.
- [ ] Run focused tests and commit the green integration.
- **Status:** pending

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
| None | 0 | — |
