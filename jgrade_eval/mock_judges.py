from __future__ import annotations

from .models import AutoLevelJudgeResult, JudgeResult, Rating


def judge_with_mock_panel(roleplay_input: dict) -> list[JudgeResult]:
    """Return deterministic mock Judge results for end-to-end smoke tests.

    This deliberately does not claim to be a real JFS evaluator. It exists so
    audio ingestion, objective-data extraction, schema handling, consensus, and
    reporting can be tested before live LLM provider adapters are configured.
    """

    return [
        _mock_judge(roleplay_input, "A", "claude", strictness=0),
        _mock_judge(roleplay_input, "B", "gpt", strictness=1),
        _mock_judge(roleplay_input, "C", "gemini", strictness=-1),
    ]


def judge_auto_cefr_with_mock_panel(roleplay_input: dict) -> list[AutoLevelJudgeResult]:
    return [
        _mock_auto_level(roleplay_input, "A", "claude", offset=0),
        _mock_auto_level(roleplay_input, "B", "gpt", offset=-1),
        _mock_auto_level(roleplay_input, "C", "gemini", offset=0),
    ]


def _mock_judge(
    roleplay_input: dict,
    judge_id: str,
    model_family: str,
    *,
    strictness: int,
) -> JudgeResult:
    transcript = str(roleplay_input.get("raw_transcript_hiragana", ""))
    metrics = roleplay_input.get("fluency_metrics", {})
    keywords = [
        str(keyword)
        for keyword in roleplay_input.get("expected_hiragana_keywords", [])
        if str(keyword).strip()
    ]

    coverage = _keyword_coverage(transcript, keywords)
    speech_ratio = float(metrics.get("speech_ratio_pct", 0.0))
    mora_per_sec = float(metrics.get("mora_per_sec", 0.0))
    max_pause = float(metrics.get("max_pause_sec", 0.0))
    transcript_len = len(transcript)

    score = 0
    if transcript_len >= 40:
        score += 1
    if speech_ratio >= 55:
        score += 1
    if mora_per_sec >= 4.0:
        score += 1
    if max_pause <= 3.0:
        score += 1
    if keywords:
        if coverage >= 0.8:
            score += 2
        elif coverage >= 0.4:
            score += 1
        else:
            score -= 1

    score -= strictness
    rating = _score_to_rating(score)
    return JudgeResult(
        judge_id=judge_id,
        model_family=model_family,
        rating=rating,
        confidence=_confidence_for(score, keywords, coverage),
        rationale=(
            "mock判定: transcript長、発話比率、発話速度、最長ポーズ、"
            "期待ひらがなキーワードの一致率で疎通確認用に判定。"
        ),
        evidence=(
            f"speech_ratio_pct={speech_ratio:.1f}",
            f"mora_per_sec={mora_per_sec:.1f}",
            f"keyword_coverage={coverage:.2f}",
        ),
        risk_flags=("mock_judge_not_valid_for_production",),
    )


def _keyword_coverage(transcript: str, keywords: list[str]) -> float:
    if not keywords:
        return 0.0
    matched = sum(1 for keyword in keywords if keyword in transcript)
    return matched / len(keywords)


def _score_to_rating(score: int) -> Rating:
    if score >= 5:
        return Rating.EXCELLENT
    if score >= 3:
        return Rating.PASS
    if score >= 1:
        return Rating.NEAR_FAIL
    return Rating.FAIL


def _confidence_for(score: int, keywords: list[str], coverage: float) -> float:
    base = 0.45 + min(max(score, 0), 5) * 0.08
    if keywords:
        base += coverage * 0.1
    return round(min(base, 0.9), 2)


def _mock_auto_level(
    roleplay_input: dict,
    judge_id: str,
    model_family: str,
    *,
    offset: int,
) -> AutoLevelJudgeResult:
    transcript = str(roleplay_input.get("raw_transcript_hiragana", ""))
    metrics = roleplay_input.get("fluency_metrics", {})
    speech_ratio = float(metrics.get("speech_ratio_pct", 0.0))
    mora_per_sec = float(metrics.get("mora_per_sec", 0.0))
    max_pause = float(metrics.get("max_pause_sec", 0.0))
    transcript_len = len(transcript)

    if transcript_len >= 450 and speech_ratio >= 75 and mora_per_sec >= 5.5 and max_pause <= 1.2:
        level_index = 3  # B2
    elif transcript_len >= 220 and speech_ratio >= 55 and mora_per_sec >= 3.8:
        level_index = 2  # B1
    elif transcript_len >= 100 and speech_ratio >= 40:
        level_index = 1  # A2
    else:
        level_index = 0  # A1

    levels = ["A1", "A2", "B1", "B2", "C1", "C2"]
    level_index = min(max(level_index + offset, 0), len(levels) - 1)
    level = levels[level_index]
    task_rating = Rating.PASS if level_index >= 1 else Rating.NEAR_FAIL
    return AutoLevelJudgeResult(
        judge_id=judge_id,
        model_family=model_family,
        predicted_cefr_level=level,
        task_rating=task_rating,
        confidence=0.55,
        rationale=(
            "mock CEFR推定: transcript長、発話率、発話速度、最長ポーズだけで"
            "疎通確認用に推定。正式判定ではありません。"
        ),
        evidence=(
            f"transcript_len={transcript_len}",
            f"speech_ratio_pct={speech_ratio:.1f}",
            f"mora_per_sec={mora_per_sec:.1f}",
        ),
        risk_flags=("mock_judge_not_valid_for_production",),
    )
