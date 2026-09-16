# Shared Fact-Module Runner Requirements

## Goal

Use one fact-module execution path after `EvidenceBundle` creation. The API and interactive console must both invoke the same runner and receive the same packet shapes for Range, Accuracy, and Coherence.

## Requirements

- The runner accepts already-built `EvidenceBundle` and never runs speech extraction or tokenisation.
- Module selection, validation, Range evidence consumption, and packet assembly exist only in the runner.
- The API preserves its existing default selection of Fluency and Range for backward-compatible responses.
- The interactive console explicitly requests all implemented fact modules, so it continues to show Range and Accuracy and additionally shows Coherence.
- Both callers construct Judge input from the runner result; selected packet keys are copied automatically without caller-specific module conditionals.
- Unselected packets are absent from both objective data and Judge input.
- No change to `EvidenceBundle`, Fluency, Range, Accuracy, or Coherence extraction algorithms.

## Acceptance criteria

1. API and console call `run_fact_modules`, not individual Range/Accuracy/Coherence collectors.
2. A single `LinguisticEvidence` instance is read by every selected text module.
3. Console output contains `=== Coherence客観データ ===` and its Judge input contains `coherence_data`.
4. Existing API default output remains byte-compatible for fact-module selection and omits Accuracy/Coherence packets.
