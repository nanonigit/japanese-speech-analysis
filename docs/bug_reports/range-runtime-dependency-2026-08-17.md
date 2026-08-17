# Range Runtime Dependency Incident — 2026-08-17

## Summary

The terminal console failed after Fluency and before Range analysis with `ModuleNotFoundError: No module named 'sudachipy'`.

## Reproduction

1. Start `./open_jgrade_console_terminal.command`.
2. Choose an audio file and complete Fluency extraction.
3. Observe the failure during Range initialization.

Minimal launcher-environment reproducer:

```sh
.venv/bin/python -c "from jgrade_eval.range import RangeExtractor; RangeExtractor.default()"
```

## Evidence and timeline

| Time | Event |
|---|---|
| Range implementation | `SudachiPy` and `SudachiDict-core` were added to `pyproject.toml`. |
| Console launch | The launcher executed `.venv/bin/python -m jgrade_eval`. |
| Failure | `.venv` could not import `sudachipy`. |
| Investigation | The system Python could import it, demonstrating that prior tests used a different interpreter. |

## Five whys

1. Why did Range fail? `sudachipy` was not importable.
2. Why was it not importable? The launcher's `.venv` did not contain it.
3. Why did `.venv` lack it? It was not synchronized after the dependency was introduced.
4. Why was that missed? The lockfile was not regenerated.
5. Why did tests not catch it? Tests ran with the system Python rather than `.venv/bin/python`.

## Fishbone

- **Dependencies:** `pyproject.toml`, lockfile, and installed environment diverged.
- **Process:** no launcher-interpreter smoke test existed.
- **Tooling:** `uv` was unavailable, so the lock update was not performed during the earlier change.
- **Code:** Range imported SudachiPy lazily, so fake-tokenizer tests did not exercise it.

## Repair and recurrence prevention

- Regenerate `uv.lock` from `pyproject.toml` and synchronize `.venv`.
- Add a default `RangeExtractor` regression test.
- Run the Range and console tests with `.venv/bin/python` before opening the terminal console.
- Retain this incident record and test command in the release checklist.
