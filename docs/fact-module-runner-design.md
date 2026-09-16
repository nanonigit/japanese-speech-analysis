# Shared Fact-Module Runner Design

`jgrade_eval/fact_modules.py` owns selection policy validation and collection after shared evidence exists.

```text
EvidenceBundle
    -> run_fact_modules(evidence, selected_modules, range_extractor)
    -> FactModuleRun(active_modules, packets)
    -> merge_objective_data(base_data)
    -> add_packets_to_roleplay_input(base_input)
```

`FactModuleRun` contains only selected packet keys (`range_data`, `accuracy_data`, `coherence_data`). Fluency remains the base facts generated from `SpeechEvidence`; it is included in selections for consistent public reporting but has no second collector.

The runner defines API defaults and supported module names. The console imports the same supported set as its explicit display profile. This is a presentation policy difference, not a second collection implementation: API retains a stable historical response by default, while the console deliberately displays all available facts.

The interactive display reads optional packet keys and prints only those present. It has no direct imports or calls to individual fact modules.
