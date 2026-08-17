# Lexical Range sequence diagram

This sequence is derived from `jgrade_eval/api_service.py` and
`jgrade_eval/range.py` after implementation.

```mermaid
sequenceDiagram
    autonumber
    participant Client as Client
    participant API as jgrade_eval/api.py
    participant Service as jgrade_eval/api_service.py

    box "Fluency module"
        participant Fluency as FluencyExtractor
    end

    box "Range module"
        participant Range as RangeExtractor
        participant Sudachi as SudachiPy
        participant Vocab as Bundled JLPT vocabulary + overrides
    end

    participant Judge as Mock / Live Judges
    participant LLM as External LLM APIs
    participant Delib as deliberation.py

    Client->>API: POST evaluation (audio)
    API->>Service: evaluate_speech_level(audio_path)
    Service->>Fluency: extract(audio_path)
    Fluency-->>Service: objective_data<br/>hiragana transcript + fluency metrics

    Service->>Range: analyze(raw_transcript_hiragana)
    Range->>Sudachi: tokenize(fixed split mode A)
    Sudachi-->>Range: surface, lemma, reading, POS tokens
    Range->>Vocab: lookup(reading)
    Vocab-->>Range: JLPT candidates + local overrides
    Range->>Range: select easiest candidate; calculate TTR and distributions
    Range-->>Service: range_data only

    Service->>Service: add range_data to objective_data
    Service->>Service: add range_data to roleplay_input

    alt mock mode
        Service->>Judge: evaluate(roleplay_input)<br/>Fluency + Range evidence
        Judge-->>Service: deterministic results
    else live mode
        Service->>Judge: evaluate(roleplay_input)<br/>Fluency + Range evidence
        Judge->>LLM: CEFR/JFS evaluation request
        LLM-->>Judge: evaluation JSON
        Judge-->>Service: results + failures
    end

    Service->>Delib: deliberate_auto_cefr(results, objective_data)
    Delib-->>Service: final decision
    Service-->>API: completed payload + objective_data
    API-->>Client: JSON response
```

## Comparison with the agreed design

The implementation matches the agreed sequence: Fluency and Range are separate
modules; SudachiPy and the vocabulary lookup remain inside Range; only the
completed `range_data` returns to the API service; and both Fluency and Range
evidence are placed in Judge input. The only intentional detail added by the
code is that the JLPT vocabulary is a bundled, pinned snapshot and accepts an
optional local override file.
