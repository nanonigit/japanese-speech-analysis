# Shared Fact-Module Runner Task Plan

1. Add RED tests proving console Coherence output/Judge input and shared runner selection behavior.
2. Add `fact_modules.py` with selection constants, `FactModuleRun`, and the runner.
3. Refactor API and console to use it; remove direct fact-module collection from each caller.
4. Update console display for optional Coherence data.
5. Run focused tests, full suite, compilation, and whitespace checks; record a Bug Hunter regression report.
