from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .live_judges import ProviderSpec, parse_provider_specs
from .prompts import AUTO_CEFR_SYSTEM_PROMPT


@dataclass(frozen=True)
class TuningProfile:
    name: str = "base"
    judge_mode: str = "mock"
    judge_providers: tuple[ProviderSpec, ...] = ()
    allow_partial_judges: bool = True
    auto_cefr_system_prompt: str = AUTO_CEFR_SYSTEM_PROMPT
    level_overrides: dict[str, str] = field(default_factory=dict)
    tuning_examples: tuple[dict[str, Any], ...] = ()
    change_history: tuple[dict[str, Any], ...] = ()
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def default(cls) -> "TuningProfile":
        return cls()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TuningProfile":
        provider_records = data.get("judge_providers", [])
        if isinstance(provider_records, str):
            providers = tuple(parse_provider_specs(provider_records))
        else:
            providers = tuple(
                ProviderSpec(
                    provider=str(record["provider"]).strip().lower(),
                    model=str(record["model"]).strip(),
                )
                for record in provider_records
            )
        return cls(
            name=str(data.get("name", "base")),
            judge_mode=str(data.get("judge_mode", "mock")),
            judge_providers=providers,
            allow_partial_judges=bool(data.get("allow_partial_judges", True)),
            auto_cefr_system_prompt=str(
                data.get("auto_cefr_system_prompt") or AUTO_CEFR_SYSTEM_PROMPT
            ),
            level_overrides={
                str(key): str(value).upper()
                for key, value in dict(data.get("level_overrides", {})).items()
            },
            tuning_examples=tuple(dict(item) for item in data.get("tuning_examples", [])),
            change_history=tuple(dict(item) for item in data.get("change_history", [])),
            notes=str(data.get("notes", "")),
            metadata=dict(data.get("metadata", {})),
        )

    def to_dict(self, *, include_history: bool = True) -> dict[str, Any]:
        payload = {
            "name": self.name,
            "judge_mode": self.judge_mode,
            "judge_providers": [
                {"provider": spec.provider, "model": spec.model}
                for spec in self.judge_providers
            ],
            "allow_partial_judges": self.allow_partial_judges,
            "auto_cefr_system_prompt": self.auto_cefr_system_prompt,
            "level_overrides": self.level_overrides,
            "tuning_examples": list(self.tuning_examples),
            "notes": self.notes,
            "metadata": self.metadata,
        }
        if include_history:
            payload["change_history"] = list(self.change_history)
        return payload


def compose_auto_cefr_system_prompt(profile: TuningProfile) -> str:
    prompt = _with_required_evidence_instruction(
        profile.auto_cefr_system_prompt or AUTO_CEFR_SYSTEM_PROMPT
    )
    correction_stats = _level_correction_stats(profile)
    if not profile.tuning_examples and not correction_stats:
        return prompt
    lines = [
        prompt.rstrip(),
        "",
        "追加チューニング指示:",
        "- 人間教師がCEFRを修正した履歴を、以後のCEFR推定に反映してください。",
        "- 同じサンプルIDだけを丸暗記せず、Raw Transcriptと流暢さ指標の特徴をCEFR判断に反映してください。",
    ]
    if correction_stats:
        lines.extend(
            [
                "",
                "補正傾向:",
                "以下はAIの直前推定から人間教師の修正CEFRへの遷移回数です。多数派の補正傾向を弱い事前分布として使ってください。",
            ]
        )
        for transition, count in sorted(correction_stats.items()):
            lines.append(f"- {transition}: {count}回")
    if not profile.tuning_examples:
        return "\n".join(lines)
    lines.extend(
        [
            "",
            "追加チューニング例:",
            "以下は人間教師の修正に基づくFew-shot参照です。",
        ]
    )
    for index, example in enumerate(profile.tuning_examples[-10:], 1):
        metrics = example.get("fluency_metrics", {})
        transcript = str(example.get("raw_transcript_hiragana", ""))[:220]
        lines.extend(
            [
                f"{index}. sample_id={example.get('sample_id', '')}",
                f"   ai_previous={example.get('previous_predicted_cefr', '')}",
                f"   human_corrected={example.get('corrected_cefr', '')}",
                (
                    "   metrics="
                    f"speech_ratio_pct={metrics.get('speech_ratio_pct', '')}, "
                    f"mora_per_sec={metrics.get('mora_per_sec', '')}, "
                    f"max_pause_sec={metrics.get('max_pause_sec', '')}"
                ),
                f"   transcript_prefix={transcript}",
                f"   note={example.get('note', '')}",
            ]
        )
    return "\n".join(lines)


def _with_required_evidence_instruction(prompt: str) -> str:
    if all(token in prompt for token in ("transcript:", "metrics:", "boundary:")):
        return prompt
    return "\n".join(
        [
            prompt.rstrip(),
            "",
            "根拠説明の必須条件:",
            "- evidenceには、Raw Transcriptに現れた意味内容・まとまりの根拠を transcript: で入れてください。",
            "- evidenceには、発話率、ポーズ、モーラ速度など流暢さ指標の根拠を metrics: で入れてください。",
            "- evidenceには、上下レベルとの境界判断を boundary: で入れてください。",
        ]
    )


def apply_level_correction(
    profile: TuningProfile,
    *,
    record: dict[str, Any],
    corrected_cefr: str,
    note: str = "",
) -> TuningProfile:
    sample_id = str(record["sample_id"])
    level = corrected_cefr.strip().upper()
    objective = record.get("objective_data") or {}
    example = {
        "created_at": _now_iso(),
        "sample_id": sample_id,
        "previous_predicted_cefr": record.get("predicted_cefr"),
        "corrected_cefr": level,
        "human_cefr": record.get("human_cefr"),
        "human_rating": record.get("human_rating"),
        "raw_transcript_hiragana": objective.get("raw_transcript_hiragana", ""),
        "fluency_metrics": objective.get("fluency_metrics", {}),
        "note": note,
    }
    updated = replace(
        profile,
        level_overrides={**profile.level_overrides, sample_id: level},
        tuning_examples=(*profile.tuning_examples, example)[-50:],
        metadata=_updated_metadata(profile, record, level),
    )
    summary = (
        f"{sample_id}: predicted {record.get('predicted_cefr') or '-'} "
        f"-> corrected {level}"
    )
    return with_history(updated, previous=profile, summary=summary)


def _updated_metadata(
    profile: TuningProfile,
    record: dict[str, Any],
    corrected_level: str,
) -> dict[str, Any]:
    metadata = dict(profile.metadata)
    stats = dict(metadata.get("level_correction_stats", {}))
    previous = str(record.get("raw_predicted_cefr") or record.get("predicted_cefr") or "").upper()
    if previous and previous != corrected_level:
        key = f"{previous}->{corrected_level}"
        stats[key] = int(stats.get(key, 0)) + 1
    metadata["level_correction_stats"] = stats
    metadata["last_tuned_at"] = _now_iso()
    return metadata


def _level_correction_stats(profile: TuningProfile) -> dict[str, int]:
    stats = profile.metadata.get("level_correction_stats", {})
    if not isinstance(stats, dict):
        return {}
    return {str(key): int(value) for key, value in stats.items()}


def with_history(
    profile: TuningProfile,
    *,
    previous: TuningProfile,
    summary: str,
) -> TuningProfile:
    entry = {
        "changed_at": _now_iso(),
        "summary": summary,
        "snapshot": previous.to_dict(include_history=False),
    }
    return replace(profile, change_history=(entry, *previous.change_history)[:10])


def restore_history(profile: TuningProfile, index: int) -> TuningProfile:
    if not 0 <= index < len(profile.change_history):
        raise IndexError("history index out of range")
    restored = TuningProfile.from_dict(profile.change_history[index]["snapshot"])
    return with_history(
        restored,
        previous=profile,
        summary=f"rollback to {profile.change_history[index]['changed_at']}",
    )


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_profile(path: Path | None) -> TuningProfile:
    if path is None or not path.exists():
        return TuningProfile.default()
    return TuningProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def save_profile(profile: TuningProfile, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
