# Lexical Range Module Design

## Boundaries

`RangeExtractor.analyze(raw_transcript_hiragana)` owns tokenisation, vocabulary lookup, ambiguity selection, and aggregation. It returns one immutable analysis result. `api_service.py` owns adding that result to its existing payloads.

## Components

- `RangeExtractor`: public deterministic facade.
- `SudachiTokenizer`: converts Sudachi morphemes into serialisable token records.
- `JLPTVocabulary`: loads a bundled base JSON file and optional local override data.
- `RangeAnalyzer`: calculates token counts, lemma counts, TTR, unknown rates, and level distributions.

## Data handling

The bundled dataset is indexed by normalised hiragana reading. Each candidate preserves source surface form and JLPT level. Overrides can add candidates, remove base candidates, or replace candidates for a reading.

## Integration

`evaluate_speech_level()` obtains Fluency data, calls `RangeExtractor.analyze()` with the transcript, stores the returned value at `objective_data["range_data"]`, and copies it into `roleplay_input["range_data"]` before Judge invocation.
