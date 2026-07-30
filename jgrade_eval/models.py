from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


CEFR_LEVELS = ["A1", "A2", "B1", "B2", "C1", "C2"]


class Rating(str, Enum):
    EXCELLENT = "◎"
    PASS = "○"
    NEAR_FAIL = "△"
    FAIL = "×"

    @classmethod
    def parse(cls, value: str | "Rating") -> "Rating":
        if isinstance(value, Rating):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            allowed = ", ".join(r.value for r in cls)
            raise ValueError(f"rating must be one of: {allowed}") from exc

    @property
    def is_passing(self) -> bool:
        return self in {Rating.EXCELLENT, Rating.PASS}


@dataclass(frozen=True)
class JudgeResult:
    judge_id: str
    model_family: str
    rating: Rating
    confidence: float
    rationale: str
    evidence: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JudgeResult":
        return cls(
            judge_id=str(data["judge_id"]),
            model_family=str(data["model_family"]),
            rating=Rating.parse(data["rating"]),
            confidence=float(data.get("confidence", 0.0)),
            rationale=str(data.get("rationale", "")),
            evidence=tuple(str(x) for x in data.get("evidence", ())),
            risk_flags=tuple(str(x) for x in data.get("risk_flags", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_id": self.judge_id,
            "model_family": self.model_family,
            "rating": self.rating.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "risk_flags": list(self.risk_flags),
        }


@dataclass(frozen=True)
class RoleplayDecision:
    roleplay_id: str
    consensus_rating: Rating
    judge_results: tuple[JudgeResult, ...]
    has_strict_majority: bool
    needs_human_review: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "roleplay_id": self.roleplay_id,
            "consensus_rating": self.consensus_rating.value,
            "judge_results": [r.to_dict() for r in self.judge_results],
            "has_strict_majority": self.has_strict_majority,
            "needs_human_review": self.needs_human_review,
        }


@dataclass(frozen=True)
class LevelDecision:
    tested_level: str
    final_level: str
    passed: bool
    roleplay_decisions: tuple[RoleplayDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tested_level": self.tested_level,
            "final_level": self.final_level,
            "passed": self.passed,
            "pass_count": sum(d.consensus_rating.is_passing for d in self.roleplay_decisions),
            "fail_count": sum(not d.consensus_rating.is_passing for d in self.roleplay_decisions),
            "needs_human_review": any(d.needs_human_review for d in self.roleplay_decisions),
            "roleplay_decisions": [d.to_dict() for d in self.roleplay_decisions],
        }


@dataclass(frozen=True)
class BenchmarkItem:
    sample_id: str
    tested_level: str
    roleplay_id: str
    human_rating: Rating
    ai_rating: Rating
    judge_disagreement: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BenchmarkItem":
        return cls(
            sample_id=str(data["sample_id"]),
            tested_level=str(data["tested_level"]),
            roleplay_id=str(data["roleplay_id"]),
            human_rating=Rating.parse(data["human_rating"]),
            ai_rating=Rating.parse(data["ai_rating"]),
            judge_disagreement=bool(data.get("judge_disagreement", False)),
        )


@dataclass(frozen=True)
class AutoLevelJudgeResult:
    judge_id: str
    model_family: str
    predicted_cefr_level: str
    task_rating: Rating
    confidence: float
    rationale: str
    evidence: tuple[str, ...] = ()
    risk_flags: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AutoLevelJudgeResult":
        level = str(data["predicted_cefr_level"]).upper()
        if level not in CEFR_LEVELS:
            allowed = ", ".join(CEFR_LEVELS)
            raise ValueError(f"predicted_cefr_level must be one of: {allowed}")
        return cls(
            judge_id=str(data["judge_id"]),
            model_family=str(data["model_family"]),
            predicted_cefr_level=level,
            task_rating=Rating.parse(data.get("task_rating", data.get("rating", "△"))),
            confidence=float(data.get("confidence", 0.0)),
            rationale=str(data.get("rationale", "")),
            evidence=tuple(str(x) for x in data.get("evidence", ())),
            risk_flags=tuple(str(x) for x in data.get("risk_flags", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "judge_id": self.judge_id,
            "model_family": self.model_family,
            "predicted_cefr_level": self.predicted_cefr_level,
            "task_rating": self.task_rating.value,
            "confidence": self.confidence,
            "rationale": self.rationale,
            "evidence": list(self.evidence),
            "risk_flags": list(self.risk_flags),
        }


@dataclass(frozen=True)
class AutoLevelDecision:
    final_cefr_level: str
    judge_results: tuple[AutoLevelJudgeResult, ...]
    has_strict_majority: bool
    needs_human_review: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "final_cefr_level": self.final_cefr_level,
            "judge_results": [result.to_dict() for result in self.judge_results],
            "has_strict_majority": self.has_strict_majority,
            "needs_human_review": self.needs_human_review,
        }
