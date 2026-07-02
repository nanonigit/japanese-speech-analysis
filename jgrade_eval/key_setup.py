from __future__ import annotations

from getpass import getpass
from pathlib import Path

from .live_judges import PROVIDER_KEY_ENVS, PROVIDER_MODEL_OPTIONS


KEY_PROMPTS = [
    *(provider for provider in PROVIDER_MODEL_OPTIONS),
    "elevenlabs",
]
KEY_ENVS = {
    **{provider: PROVIDER_KEY_ENVS[provider][0] for provider in PROVIDER_MODEL_OPTIONS},
    "elevenlabs": "ELEVENLABS_API_KEY",
}


def configure_keys(env_path: Path) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_env(env_path)

    print(f"APIキーを {env_path} に設定します。入力は画面に表示されません。")
    print("空のままEnterを押すと、そのプロバイダは変更しません。")

    for provider in KEY_PROMPTS:
        primary_env = KEY_ENVS[provider]
        current = "set" if existing.get(primary_env) else "missing"
        value = getpass(f"{provider} ({primary_env}, current={current}): ").strip()
        if value:
            existing[primary_env] = value
            print(f"  -> {provider}: set")
        elif existing.get(primary_env):
            print(f"  -> {provider}: unchanged (set)")
        else:
            print(f"  -> {provider}: missing")

    _write_env(env_path, existing)
    print(f"wrote {env_path}")
    print("\n現在の設定状態:")
    for provider in KEY_PROMPTS:
        primary_env = KEY_ENVS[provider]
        state = "set" if existing.get(primary_env) else "missing"
        print(f"  {provider}: {state} ({primary_env})")


def _read_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("'").strip('"')
    return values


def _write_env(path: Path, values: dict[str, str]) -> None:
    ordered_keys = [
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "XAI_API_KEY",
        "GROQ_API_KEY",
        "ELEVENLABS_API_KEY",
    ]
    lines = [
        "# Local API keys for J-GRADE. This file is ignored by git.",
        "# Never commit real API keys.",
    ]
    for key in ordered_keys:
        lines.append(f"{key}={values.get(key, '')}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
