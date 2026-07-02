from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .live_judges import ProviderSpec, parse_provider_specs


DEFAULT_JUDGE_CONFIG_PATH = Path("config/judge_llms.json")


@dataclass(frozen=True)
class JudgeConsoleConfig:
    judge_mode: str = "mock"
    audio_dir: Path = Path("audio")
    profile_path: Path | None = Path("tuning_profiles/base.json")
    judge_providers: tuple[ProviderSpec, ...] = ()


def load_judge_console_config(path: Path | None = DEFAULT_JUDGE_CONFIG_PATH) -> JudgeConsoleConfig:
    if path is None or not path.exists():
        return JudgeConsoleConfig()

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("judge config must be a JSON object.")

    judge_mode = str(data.get("judge_mode", "mock")).strip().lower()
    if judge_mode not in {"mock", "live"}:
        raise ValueError("judge_mode must be 'mock' or 'live'.")

    profile_value = data.get("profile", "tuning_profiles/base.json")
    profile_path = Path(profile_value) if profile_value else None

    return JudgeConsoleConfig(
        judge_mode=judge_mode,
        audio_dir=Path(str(data.get("audio_dir", "audio"))),
        profile_path=profile_path,
        judge_providers=tuple(_parse_configured_providers(data)),
    )


def _parse_configured_providers(data: dict[str, Any]) -> list[ProviderSpec]:
    raw = data.get("judge_providers", data.get("live_judges", []))
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        return parse_provider_specs(raw)
    if not isinstance(raw, list):
        raise ValueError("judge_providers/live_judges must be a string or array.")

    specs: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("each judge provider entry must be an object.")
        if item.get("enabled", True) is False:
            continue
        provider = str(item.get("provider", "")).strip().lower()
        model = str(item.get("model", "")).strip()
        if not provider or not model:
            raise ValueError("each enabled judge provider requires provider and model.")
        specs.append(f"{provider}:{model}")

    return parse_provider_specs(",".join(specs)) if specs else []
