# J-GRADE Evaluation Engine

This module is the local, testable backend core for J-GRADE task-achievement evaluation.
It does not require live LLM API keys for local validation: fixture judge outputs are used to verify prompts, consensus, CEFR pass/fail conditionals, and human-vs-AI metrics.

For the full input, processing, output, and future API contract, see
`docs/jgrade_system_io_api.md`.

## Local Commands

Build a provider-agnostic judge prompt:

```bash
uv run python -m jgrade_eval prompt \
  --input examples/jgrade_roleplay_input.json \
  --judge A \
  --model-family claude
```

Run the consensus gate against three judge outputs per roleplay:

```bash
uv run python -m jgrade_eval consensus \
  --input examples/jgrade_judge_results.json \
  --output outputs/jgrade_decision.json
```

Compare AI consensus labels against human teacher benchmark labels:

```bash
uv run python -m jgrade_eval benchmark \
  --input examples/jgrade_benchmark.json \
  --output outputs/jgrade_benchmark_report.json
```

Run the full local audio pipeline against a manifest:

```bash
uv run python -m jgrade_eval extract-objective \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --output outputs/jgrade_objective_data.json

uv run python -m jgrade_eval evaluate-audio \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --judge-mode mock \
  --output outputs/jgrade_audio_report.json

uv run python -m jgrade_eval evaluate-audio \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --judge-mode live \
  --judge-providers anthropic:claude-sonnet-4-6,openai:gpt-5.4-mini,gemini:gemini-3.1-pro-preview \
  --output outputs/jgrade_live_report.json

uv run python -m jgrade_eval interactive --judge-mode mock

uv run python -m jgrade_eval configure-keys

uv run python -m jgrade_eval interactive --judge-mode live

uv run python -m jgrade_eval interactive \
  --judge-mode live \
  --judge-providers anthropic:claude-sonnet-4-6,openai:gpt-5.4-mini,gemini:gemini-3.1-pro-preview

uv run python -m jgrade_eval download-jfs-samples \
  --output data/external/jfs_roleplay/download_manifest.json

uv run python -m jgrade_eval prepare-jfs-dataset \
  --output data/tuning/jfs_roleplay_dataset.json

uv run python -m jgrade_eval.tuning_runner \
  --dataset data/tuning/jfs_roleplay_dataset.json \
  --profile tuning_profiles/base.json \
  --out outputs/jfs_roleplay_tuning_report.json
```

`extract-objective` stops after the repository's `fluency.py`-based objective
data extraction. Use it when you want to inspect the raw hiragana transcript,
speech ratio, mora speed, pauses, and speech segments before any JFS Judge logic
runs.

`interactive` is the CLI operator flow. It asks which audio file to evaluate,
displays the extracted objective data, then prints 1 to 3 Judge CEFR predictions
and the CEFR aggregation result. It does not ask the operator to enter a target
CEFR level, roleplay task, can-do criteria, or expected information. The default
production shape is still three independent providers, but the local CLI can run
with one or two providers for debugging. If one live Judge fails in interactive
mode, the CLI prints a warning and continues with the successful Judge results
as long as at least one provider returned a valid decision.

Audio selection is not limited to repository samples. The operator can open a
macOS file picker, paste or drag-and-drop any supported audio file path, or
choose a sample from `audio/`.

In live mode, omit `--judge-providers` to choose Judge A/B/C providers and
models by number. Already-selected providers are hidden from later Judge choices,
and Judge B/C can be skipped. Use `configure-keys` to write a local `.env` file;
key input is hidden, each provider reports only `set/missing`, and `.env` is
ignored by git.

`judge-mode mock` is a deterministic smoke test. It verifies that audio files can
be loaded, objective data can be extracted, Judge-shaped CEFR predictions
can be generated, and the consensus gate can produce a CEFR decision. It is not
a valid JFS score. Production scoring should use live providers returning the
same auto-level JSON shape.

## Official JFS Sample Dataset

`examples/jfs_roleplay_catalog.json` tracks the official Japan Foundation JF
Standard role-play sample metadata: source page, sample page, audio URL,
evaluation PDF URL, CEFR/JFS level, task rating, role-play task, and local
Can-do criteria. Test audio is managed in `audio/`; official JF audio files are
ignored by git. Evaluation PDFs and download manifests are stored under
`data/external/jfs_roleplay/`, which is ignored by git.

The current official sample coverage is A2, B1, B2, and C1. The JF role-play
test can be used to estimate A1 to C1-or-above, but the official source used
here does not provide C2 role-play samples. Treat any C2 prediction as requiring
human review until a validated C2 source is added.

These samples are meant for calibration and validation, not blind test leakage.
Use them to inspect whether each Judge explains the CEFR decision with both
hiragana transcript evidence and fluency metrics, then benchmark exact and
adjacent-level accuracy before changing prompts or profile examples.

## Live Judge Providers

Live mode reads secrets from the process environment or from a local `.env` file.
Never commit `.env`.

```bash
cp .env.example .env
uv run python -m jgrade_eval configure-keys
```

Supported text Judge providers:

| Provider | API key env var | Example provider spec |
| --- | --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic:claude-sonnet-4-6` |
| OpenAI | `OPENAI_API_KEY` | `openai:gpt-5.4-mini` |
| Gemini | `GEMINI_API_KEY` or `GOOGLE_API_KEY` | `gemini:gemini-3.1-pro-preview` |
| xAI | `XAI_API_KEY` | `xai:grok-4.3` |
| Groq | `GROQ_API_KEY` | `groq:openai/gpt-oss-120b` |

Choose exactly three entries in `--judge-providers`; they become Judge A, Judge B, and Judge C in order. `configure-keys` can store an `ELEVENLABS_API_KEY`, but `elevenlabs` is intentionally not enabled as a text Judge provider because this pipeline evaluates transcript text and timing data, not speech synthesis.

Run the deterministic test suite:

```bash
uv run python -m unittest discover -s tests
```

## Data Flow

1. `fluency.py` or `phase3_batch.py` produces raw hiragana transcript and timing metrics.
2. The CLI/API layer creates one roleplay input payload with optional task context.
3. Three independent judge adapters call the selected LLM providers with the same auto-CEFR prompt contract.
4. `AutoCefrConsensus` reduces the three CEFR predictions to one final CEFR level by majority vote.
5. Phase 1 benchmark reports compare the AI labels with human teacher labels.

## AWS/Web App Integration Target

Keep this package as the pure service layer. For production, wrap it with a thin API layer:

- API request: raw hiragana transcript, fluency metrics, and optional roleplay task context.
- Async fan-out: call Claude/GPT/Gemini adapters concurrently.
- API response: Judge CEFR predictions, final CEFR decision, confidence/evidence, and human-review flags.
- Storage: persist request payloads, judge raw JSON, final decision, latency, cost, and benchmark labels when available.
- Monitoring: track accuracy, macro F1, `○`/`△` boundary confusions, judge disagreement rate, latency, and provider failures.

The current local fixture path is intentionally deterministic so prompt and consensus changes can be regression-tested before adding live provider calls.

## Audio Manifest Shape

Prepare one manifest per tested candidate/level. Use three roleplays when applying the current pass/fail rule.

```json
{
  "sample_id": "candidate-b1-001",
  "tested_level": "B1",
  "speaker_metadata": {
    "first_language": "vietnamese"
  },
  "roleplays": [
    {
      "roleplay_id": "rp-1",
      "audio_path": "audio/candidate-b1-rp1.mp3",
      "roleplay_task": "市役所の窓口で、必要書類と提出期限を質問する。",
      "jfs_can_do_criteria": [
        "身近な公的手続きについて、必要な情報を質問できる。"
      ],
      "optional_expected_information": [
        "必要書類を尋ねる",
        "提出期限を尋ねる"
      ],
      "expected_hiragana_keywords": [
        "ひつよう",
        "いつまで"
      ]
    }
  ]
}
```
