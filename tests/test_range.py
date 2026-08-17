from __future__ import annotations

import unittest

from jgrade_eval.range import JLPTVocabulary, RangeExtractor, TokenizedWord


class FakeTokenizer:
    def __init__(self, tokens: list[TokenizedWord]) -> None:
        self.tokens = tokens

    def tokenize(self, text: str) -> list[TokenizedWord]:
        return self.tokens


class RangeExtractorTests(unittest.TestCase):
    def test_default_extractor_runs_with_the_bundled_sudachi_dependencies(self) -> None:
        data = RangeExtractor.default().analyze("わたしはすしがすきです")

        self.assertEqual(data["tokenizer_version"].split(" ", 1)[0], "SudachiPy")
        self.assertEqual(data["split_mode"], "A")
        self.assertEqual(data["statistics"]["token_count"], 6)

    def test_reports_lexical_statistics_and_jlpt_distribution(self) -> None:
        tokenizer = FakeTokenizer(
            [
                TokenizedWord("わたし", "私", "わたし", ("名詞",)),
                TokenizedWord("は", "は", "は", ("助詞",)),
                TokenizedWord("すし", "寿司", "すし", ("名詞",)),
                TokenizedWord("が", "が", "が", ("助詞",)),
                TokenizedWord("すき", "好き", "すき", ("形状詞",)),
                TokenizedWord("です", "です", "です", ("助動詞",)),
            ]
        )
        vocabulary = JLPTVocabulary.from_entries(
            [
                {"surface": "私", "reading": "わたし", "level": 5},
                {"surface": "寿司", "reading": "すし", "level": 5},
                {"surface": "好き", "reading": "すき", "level": 5},
            ],
            version="test-base",
        )

        data = RangeExtractor(tokenizer, vocabulary).analyze("わたしはすしがすきです")

        self.assertEqual(data["statistics"]["token_count"], 6)
        self.assertEqual(data["statistics"]["lexical_token_count"], 3)
        self.assertEqual(data["statistics"]["unique_lemma_count"], 3)
        self.assertEqual(data["statistics"]["ttr"], 1.0)
        self.assertEqual(data["statistics"]["known_token_count"], 3)
        self.assertEqual(data["statistics"]["unknown_token_count"], 0)
        self.assertEqual(data["jlpt_distribution"]["N5"]["token_count"], 3)
        self.assertEqual(data["tokens"][1]["is_lexical"], False)

    def test_uses_easiest_level_for_homophones_and_retains_candidates(self) -> None:
        token = TokenizedWord("ひく", "ひく", "ひく", ("動詞",))
        vocabulary = JLPTVocabulary.from_entries(
            [
                {"surface": "引く", "reading": "ひく", "level": 5},
                {"surface": "弾く", "reading": "ひく", "level": 4},
                {"surface": "惹く", "reading": "ひく", "level": 1},
            ],
            version="test-base",
        )

        data = RangeExtractor(FakeTokenizer([token]), vocabulary).analyze("ひく")

        self.assertEqual(data["ambiguity_count"], 1)
        self.assertEqual(data["tokens"][0]["selected_jlpt_level"], "N5")
        self.assertEqual(len(data["tokens"][0]["jlpt_candidates"]), 3)

    def test_marks_unmatched_lexical_tokens_as_unknown(self) -> None:
        token = TokenizedWord("みち", "未知", "みち", ("名詞",))
        vocabulary = JLPTVocabulary.from_entries([], version="test-base")

        data = RangeExtractor(FakeTokenizer([token]), vocabulary).analyze("みち")

        self.assertEqual(data["statistics"]["unknown_token_count"], 1)
        self.assertEqual(data["statistics"]["unknown_token_rate"], 1.0)
        self.assertIsNone(data["tokens"][0]["selected_jlpt_level"])

    def test_applies_reading_override_before_base_candidates(self) -> None:
        token = TokenizedWord("すし", "寿司", "すし", ("名詞",))
        vocabulary = JLPTVocabulary.from_entries(
            [{"surface": "寿司", "reading": "すし", "level": 5}],
            overrides={"すし": [{"surface": "寿司", "reading": "すし", "level": 3}]},
            version="test-base",
        )

        data = RangeExtractor(FakeTokenizer([token]), vocabulary).analyze("すし")

        self.assertEqual(data["tokens"][0]["selected_jlpt_level"], "N3")
        self.assertEqual(data["dictionary_version"], "test-base")

    def test_returns_a_complete_empty_analysis(self) -> None:
        data = RangeExtractor(FakeTokenizer([]), JLPTVocabulary.from_entries([], version="test-base")).analyze("")

        self.assertEqual(data["statistics"]["token_count"], 0)
        self.assertEqual(data["statistics"]["ttr"], 0.0)
        self.assertEqual(data["tokens"], [])


if __name__ == "__main__":
    unittest.main()
