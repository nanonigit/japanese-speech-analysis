# Accuracy Module Implementation Plan

## Phase 1 — Contracts and tests

1. Add failing unit tests for `AsrUnitEvidence`, `AsrAlignmentEvidence`, and `AccuracyFactPacket` serialization.
2. Add negative tests that reject `score`, `correct`, `error`, and CEFR fields from Accuracy output.
3. Add tests for explicit unavailable capability records and optional reference differences.

## Phase 2 — Common capability extension

1. Introduce Evidence schema v2 additively; old v1 cache entries remain readable or are bypassed by schema-key change.
2. Add `AsrAlignmentProvider` and a Wav2Vec2 CTC adapter that derives compact per-unit summaries from existing logits.
3. Extend `FluencyExtractor` handoff without serializing raw logits.
4. Include alignment-provider identity and decoder configuration in cache provenance.

## Phase 3 — Independent Accuracy module

1. Add `jgrade_eval/accuracy.py` with a `collect(bundle, reference=None)` interface.
2. Reuse `LinguisticEvidence` for morphology observations; do not tokenize again.
3. Add deterministic reference alignment behind an explicit reference option.
4. Add capability/status fields and fact-only serialization.

## Phase 4 — Orchestration and delivery

1. Add `ModuleRunner` and selected-module request configuration while preserving current Fluency/Range API compatibility.
2. Integrate Accuracy FactPacket only when selected; keep downstream Judge as the sole evaluator.
3. Add API, CLI, cache, and module-isolation regression tests.
4. Run unit tests, compile checks, diff review, and a teacher-reviewed fixture set before enabling in a live Judge prompt.

## Exit criteria

- Accuracy can run alone, with Range, or with all selected modules.
- Its output consists exclusively of versioned observations and capability status.
- An ASR uncertainty value is never renamed or interpreted as learner correctness.
- Reference differences are impossible without an explicit reference transcript.
- Model choice/calibration remains a replaceable provider decision, documented with validation evidence.
