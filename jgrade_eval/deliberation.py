from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from .consensus import AutoCefrConsensus
from .models import AutoLevelDecision, AutoLevelJudgeResult
from .tuning_profile import TuningProfile


@dataclass(frozen=True)
class CalibrationMatch:
    sample_id: str
    previous_level: str
    corrected_level: str
    score: float
    summary: str


@dataclass(frozen=True)
class AutoCefrDeliberation:
    raw_decision: AutoLevelDecision
    final_decision: AutoLevelDecision
    judge_summaries: tuple[str, ...]
    calibration_matches: tuple[CalibrationMatch, ...]
    conclusion: str
    applied_calibration: bool


def deliberate_auto_cefr(
    judge_results: list[AutoLevelJudgeResult] | tuple[AutoLevelJudgeResult, ...],
    *,
    objective_data: dict[str, Any],
    profile: TuningProfile | None,
) -> AutoCefrDeliberation:
    raw_decision = AutoCefrConsensus().decide(judge_results)
    matches = _matching_calibration_examples(
        profile,
        raw_level=raw_decision.final_cefr_level,
        objective_data=objective_data,
    )
    final_level, applied, calibration_reason = _choose_final_level(raw_decision, matches)
    final_decision = raw_decision
    if applied and final_level != raw_decision.final_cefr_level:
        final_decision = AutoLevelDecision(
            final_cefr_level=final_level,
            judge_results=raw_decision.judge_results,
            has_strict_majority=raw_decision.has_strict_majority,
            needs_human_review=True,
        )

    return AutoCefrDeliberation(
        raw_decision=raw_decision,
        final_decision=final_decision,
        judge_summaries=_summarize_judges(judge_results),
        calibration_matches=tuple(matches),
        conclusion=_build_conclusion(raw_decision, final_decision, matches, calibration_reason),
        applied_calibration=applied,
    )


def _summarize_judges(
    judge_results: list[AutoLevelJudgeResult] | tuple[AutoLevelJudgeResult, ...],
) -> tuple[str, ...]:
    summaries: list[str] = []
    for result in judge_results:
        evidence = "; ".join(result.evidence[:2]) if result.evidence else "根拠なし"
        summaries.append(
            f"Judge {result.judge_id} [{result.model_family}]: "
            f"{result.predicted_cefr_level}, task={result.task_rating.value}, "
            f"confidence={result.confidence:.2f}; {result.rationale}; evidence={evidence}"
        )
    return tuple(summaries)


def _matching_calibration_examples(
    profile: TuningProfile | None,
    *,
    raw_level: str,
    objective_data: dict[str, Any],
) -> list[CalibrationMatch]:
    if not profile:
        return []

    current_metrics = objective_data.get("fluency_metrics", {})
    current_transcript = str(objective_data.get("raw_transcript_hiragana", ""))
    matches: list[CalibrationMatch] = []
    for example in profile.tuning_examples:
        previous = str(example.get("previous_predicted_cefr", "")).upper()
        corrected = str(example.get("corrected_cefr", "")).upper()
        if previous != raw_level or corrected == raw_level:
            continue
        score = _calibration_similarity(
            current_metrics,
            example.get("fluency_metrics", {}),
            len(current_transcript),
            len(str(example.get("raw_transcript_hiragana", ""))),
        )
        if score < 0.55:
            continue
        matches.append(
            CalibrationMatch(
                sample_id=str(example.get("sample_id", "")),
                previous_level=previous,
                corrected_level=corrected,
                score=score,
                summary=(
                    f"{previous}->{corrected}, similarity={score:.2f}, "
                    f"speech_ratio={example.get('fluency_metrics', {}).get('speech_ratio_pct', 'n/a')}, "
                    f"mora_per_sec={example.get('fluency_metrics', {}).get('mora_per_sec', 'n/a')}, "
                    f"max_pause={example.get('fluency_metrics', {}).get('max_pause_sec', 'n/a')}"
                ),
            )
        )
    return sorted(matches, key=lambda match: match.score, reverse=True)[:5]


def _calibration_similarity(
    current_metrics: dict[str, Any],
    example_metrics: dict[str, Any],
    current_transcript_len: int,
    example_transcript_len: int,
) -> float:
    speech_ratio = _numeric_similarity(
        current_metrics.get("speech_ratio_pct"),
        example_metrics.get("speech_ratio_pct"),
        tolerance=25.0,
    )
    mora_speed = _numeric_similarity(
        current_metrics.get("mora_per_sec"),
        example_metrics.get("mora_per_sec"),
        tolerance=2.5,
    )
    max_pause = _numeric_similarity(
        current_metrics.get("max_pause_sec"),
        example_metrics.get("max_pause_sec"),
        tolerance=5.0,
    )
    transcript_len = _numeric_similarity(
        current_transcript_len,
        example_transcript_len,
        tolerance=max(current_transcript_len, example_transcript_len, 1) * 0.75,
    )
    return round(
        0.30 * speech_ratio
        + 0.30 * mora_speed
        + 0.25 * max_pause
        + 0.15 * transcript_len,
        3,
    )


def _numeric_similarity(value_a: Any, value_b: Any, *, tolerance: float) -> float:
    try:
        a = float(value_a)
        b = float(value_b)
    except (TypeError, ValueError):
        return 0.0
    if tolerance <= 0:
        return 0.0
    return max(0.0, 1.0 - abs(a - b) / tolerance)


def _choose_final_level(
    raw_decision: AutoLevelDecision,
    matches: list[CalibrationMatch],
) -> tuple[str, bool, str]:
    if not matches:
        return raw_decision.final_cefr_level, False, "該当する補正例はありません。"

    counts = Counter(match.corrected_level for match in matches)
    corrected_level, count = counts.most_common(1)[0]
    best_score = max(match.score for match in matches if match.corrected_level == corrected_level)
    if count >= 1 and best_score >= 0.70:
        return (
            corrected_level,
            corrected_level != raw_decision.final_cefr_level,
            f"類似補正例 {count}件 が {raw_decision.final_cefr_level}->{corrected_level} を支持しました。",
        )
    return (
        raw_decision.final_cefr_level,
        False,
        "補正例はありますが、類似度または件数が弱いため多数決を維持しました。",
    )


def _build_conclusion(
    raw_decision: AutoLevelDecision,
    final_decision: AutoLevelDecision,
    matches: list[CalibrationMatch],
    calibration_reason: str,
) -> str:
    vote_counts = Counter(result.predicted_cefr_level for result in raw_decision.judge_results)
    votes = ", ".join(f"{level}={count}" for level, count in sorted(vote_counts.items()))
    majority = "厳密な多数決あり" if raw_decision.has_strict_majority else "厳密な多数決なし"
    if final_decision.final_cefr_level != raw_decision.final_cefr_level:
        return (
            f"Judge投票は {votes} で raw={raw_decision.final_cefr_level} ({majority})。"
            f"ただし {calibration_reason} "
            f"最終CEFRは {final_decision.final_cefr_level} とし、人間確認を必要にしました。"
        )
    if matches:
        return (
            f"Judge投票は {votes} で {final_decision.final_cefr_level} ({majority})。"
            f"{calibration_reason} 最終CEFRは多数決を維持しました。"
        )
    return (
        f"Judge投票は {votes} で {final_decision.final_cefr_level} ({majority})。"
        "補正例による変更はなく、最終CEFRはJudge協議結果を採用しました。"
    )
