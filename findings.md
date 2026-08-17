# Findings: Objective lexical Range module

## Requirements

- Accept the Fluency output `raw_transcript_hiragana`.
- Use SudachiPy with a fixed dictionary package and split mode.
- Produce deterministic token, vocabulary, TTR, unknown-word, and ambiguity evidence.
- Keep analysis free from LLMs and external runtime APIs.
- Put resulting `range_data` into `objective_data` and the Judge's `roleplay_input`.
- Commit independently validated stages and roll back to the last green commit before retrying a repeated test failure.

## Current architecture

- `FluencyExtractor.extract()` returns `objective_data` with `raw_transcript_hiragana` and `fluency_metrics`.
- `evaluate_speech_level()` creates `roleplay_input`, invokes mock or live Judges, then invokes deliberation.
- The API tests replace `FluencyExtractor` with a lightweight fake, so Range integration must remain injectable or deterministic in tests.

## Console evidence presentation

- The interactive console currently labels the complete extraction step as one generic objective-data stage, although Fluency and Range are distinct deterministic modules.
- It also prints a single combined objective-data heading and calls `prompt_user_cefr_level()` after the Judge and deliberation stages.
- The revised console must expose Fluency and Range as separate processing/evidence stages, pass `range_data` to the Judge input, and defer manual CEFR correction rather than prompting during evidence-focused runs.

## Runtime dependency incident: 2026-08-17

- **Observed symptom:** the terminal console completed Fluency, then failed at Range with `ModuleNotFoundError: No module named 'sudachipy'`.
- **Reproduction:** `.venv/bin/python -c "from jgrade_eval.range import RangeExtractor; RangeExtractor.default()"` fails; the system `python3` succeeds.
- **Immediate cause:** the launcher always uses `.venv/bin/python`, but that environment lacks both `SudachiPy` and `SudachiDict-core`.
- **Root cause:** the Range dependency was added to `pyproject.toml` without synchronizing `uv.lock` and the already-created `.venv`; prior tests ran with the system Python rather than the launcher interpreter.
- **Repair contract:** add a default-extractor test and execute it with `.venv/bin/python`; regenerate the lock and synchronize `.venv` before console smoke testing.

## Dictionary research

- The selected `JLPT_vocab_ALL.json` records readings and numerical JLPT levels where N1 is `1` and N5 is `5`.
- The upstream data must be bundled at a fixed revision with its attribution and license recorded.
- TUFS CEFR-Jx28 lists are translated from an English CEFR-J list and are not suitable as a sole Japanese lexical-level authority.

## Resources

- `jgrade_eval/audio_pipeline.py`
- `jgrade_eval/api_service.py`
- `jgrade_eval/prompts.py`
- `tests/test_jgrade_api.py`
- https://raw.githubusercontent.com/Bluskyo/JLPT_Vocabulary/main/data/vocab/results/JLPT_vocab_ALL.json
