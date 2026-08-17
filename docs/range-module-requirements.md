# Lexical Range Module Requirements

## Scope

This module objectively measures lexical Range evidence from the hiragana transcript produced by Fluency. It does not determine final CEFR/JFS level, grammar range, paraphrase ability, or lexical accuracy.

## Inputs and outputs

- Input: `raw_transcript_hiragana: str`.
- Output: versioned `range_data` with tokens, statistics, JLPT distribution, ambiguity count, and analysis metadata.
- The API service adds the output to `objective_data` and `roleplay_input`.

## Rules

- Analysis is deterministic and makes no LLM or external runtime API call.
- Use a fixed SudachiPy dictionary and split mode.
- Use lemma-level lexical statistics; include only lexical parts of speech in TTR and JLPT distributions.
- Treat unmatched lexical tokens as unknown; do not classify them as simple vocabulary.
- For same-reading candidates, select the easiest JLPT candidate while retaining all candidates for auditability.
- Treat JLPT levels as vocabulary evidence only, not as a direct CEFR conversion.

## Acceptance criteria

- Tokenise `わたしはすしがすきです` predictably.
- Correctly report token and lemma statistics, known/unknown counts, and N5--N1 distributions.
- Cover empty input, unknown tokens, ambiguity, and local overrides.
- Expose identical Range evidence to the API response and live Judge request.
