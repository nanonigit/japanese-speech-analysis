from __future__ import annotations

import shlex
import subprocess
import os
from dataclasses import replace
from getpass import getpass
from pathlib import Path

from .audio_pipeline import FluencyExtractor, ObjectiveExtractionError
from .consensus import AutoCefrConsensus
from .live_judges import (
    PROVIDER_KEY_ENVS,
    PROVIDER_MODEL_OPTIONS,
    ProviderSpec,
    format_provider_spec,
    judge_auto_cefr_with_live_panel_partial,
    missing_key_envs,
    provider_key_status,
)
from .mock_judges import judge_auto_cefr_with_mock_panel
from .models import (
    CEFR_LEVELS,
    AutoLevelDecision,
    AutoLevelJudgeResult,
    JudgeResult,
    RoleplayDecision,
)
from .tuning_profile import (
    TuningProfile,
    apply_level_correction,
    compose_auto_cefr_system_prompt,
    load_profile,
    save_profile,
)
from .tuning_samples import (
    DEFAULT_REVIEW_DATASET_PATH,
    append_judged_sample,
    make_review_sample_id,
)


AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".flac", ".ogg")


def run_interactive(
    *,
    audio_dir: Path,
    judge_mode: str,
    provider_specs: list[ProviderSpec] | None,
    timeout_sec: float,
    profile_path: Path | None = None,
    review_store_path: Path | None = DEFAULT_REVIEW_DATASET_PATH,
) -> None:
    judge_mode, provider_specs = prompt_judge_setup(judge_mode, provider_specs or [])
    audio_path = prompt_audio_choice(list_audio_files(audio_dir))

    print("\n[1/4] 客観データを抽出中...")
    try:
        extractor = FluencyExtractor()
        objective_data = extractor.extract(audio_path)
    except ObjectiveExtractionError as exc:
        print("\n[エラー] 客観データ抽出に失敗しました。")
        print(str(exc))
        raise SystemExit(2) from exc
    print_objective_data(objective_data)
    profile = load_profile(profile_path) if profile_path else None
    review_sample_id = make_review_sample_id(audio_path, objective_data)

    if judge_mode == "live" and not provider_specs:
        provider_specs = prompt_provider_specs()
    if judge_mode == "live":
        _ensure_live_keys_available(provider_specs or [])

    roleplay_input = {
        "sample_id": review_sample_id,
        "target_cefr_level": "auto",
        "roleplay_id": "rp-1",
        "roleplay_task": "不明",
        "jfs_can_do_criteria": [],
        "raw_transcript_hiragana": objective_data["raw_transcript_hiragana"],
        "fluency_metrics": objective_data["fluency_metrics"],
        "speaker_metadata": {},
        "optional_expected_information": [],
    }

    judge_count = len(provider_specs) if judge_mode == "live" and provider_specs else 3
    print(f"\n[2/4] {judge_count} JudgeでCEFRレベルを自動推定中...")
    if judge_mode == "mock":
        auto_results = judge_auto_cefr_with_mock_panel(roleplay_input)
        judge_failures = []
        print("注: judge-mode=mock は疎通確認用です。正式なCEFR判定ではありません。")
    elif judge_mode == "live":
        if not provider_specs:
            raise ValueError("provider_specs are required when judge_mode='live'.")
        auto_results, judge_failures = judge_auto_cefr_with_live_panel_partial(
            roleplay_input,
            provider_specs,
            timeout_sec=timeout_sec,
            system_prompt=compose_auto_cefr_system_prompt(profile) if profile else None,
        )
        if judge_failures:
            print("\n[警告] 一部のLLM Judge呼び出しに失敗しました。")
            for failure in judge_failures:
                print(f"  Judge {failure.judge_id}: {failure.message}")
            if auto_results:
                print("成功したJudgeだけでCEFR集約を続行します。")
        if not auto_results:
            print("\n[エラー] LLM Judge呼び出しに失敗しました。")
            print("すべてのJudgeが失敗したため、CEFR集約を実行できません。")
            print("モデルID、APIキー、ネットワーク、またはプロバイダ側の応答形式を確認してください。")
            raise SystemExit(2)
    else:
        raise ValueError("judge_mode must be 'mock' or 'live'.")

    print_auto_level_judge_results(auto_results)

    print("\n[3/4] CEFR多数決を計算中...")
    decision = AutoCefrConsensus().decide(auto_results)
    raw_decision = decision
    override_level = profile.level_overrides.get(review_sample_id) if profile else None
    if override_level:
        decision = replace(
            decision,
            final_cefr_level=override_level,
            needs_human_review=True,
        )
    print_auto_cefr_consensus(decision)
    if override_level:
        print(f"プロファイル補正: raw={raw_decision.final_cefr_level} -> tuned={override_level}")

    print_console_final_result(
        objective_data=objective_data,
        decision=decision,
        judge_results=auto_results,
    )

    record = _build_review_record(
        audio_path=audio_path,
        review_sample_id=review_sample_id,
        objective_data=objective_data,
        decision=decision,
        raw_decision=raw_decision,
        auto_results=auto_results,
        judge_failures=judge_failures,
        override_applied=bool(override_level),
    )
    user_level = prompt_user_cefr_level(decision.final_cefr_level)
    if user_level:
        record["human_cefr"] = user_level
        record["human_feedback_source"] = "console_final_prompt"
        if user_level == decision.final_cefr_level:
            print("\n=== ユーザー補正 ===")
            print(f"ユーザー選択: {user_level}")
            print("SystemJudgeの判定と一致したため、判定過程の修正は行いません。")
        else:
            previous_level = decision.final_cefr_level
            correction_record = {
                **record,
                "predicted_cefr": previous_level,
                "raw_predicted_cefr": previous_level,
            }
            profile = apply_and_save_user_level_correction(
                profile=profile or TuningProfile.default(),
                profile_path=profile_path,
                record=correction_record,
                corrected_level=user_level,
            )
            decision = replace(
                decision,
                final_cefr_level=user_level,
                needs_human_review=True,
            )
            record = {
                **record,
                "predicted_cefr": user_level,
                "user_corrected_cefr": user_level,
                "system_predicted_cefr_before_feedback": previous_level,
                "profile_override_applied": True,
                "human_feedback_applied": True,
                "needs_human_review": True,
            }
            print_user_level_correction_summary(
                sample_id=review_sample_id,
                previous_level=previous_level,
                corrected_level=user_level,
                profile_path=profile_path,
                profile=profile,
            )
            print_console_final_result(
                objective_data=objective_data,
                decision=decision,
                judge_results=auto_results,
                title="修正後の最終結果",
            )
    else:
        print("\nユーザーレベル選択はスキップされました。")

    if review_store_path:
        append_judged_sample(review_store_path, record=record, source="interactive")
        print(f"判定履歴を保存しました: {review_store_path}")

    print("\n[4/4] 完了")
    print("注: これは選択した1音声に対するCEFR推定です。")
    print("公開・本番利用前には、人間教師ラベルとのベンチマークで精度検証してください。")


def prompt_judge_setup(
    judge_mode: str,
    provider_specs: list[ProviderSpec],
) -> tuple[str, list[ProviderSpec] | None]:
    configured_specs = list(provider_specs)
    while True:
        print("\n=== Judge設定 ===")
        print("最初に評価に使うJudgeを選んでください。")
        print("APIキーの値は表示しません。設定済みかどうかだけ表示します。")
        if configured_specs:
            print_provider_key_summary(configured_specs)
        else:
            print("設定済みの実LLM Judge候補: なし")

        options: list[tuple[str, str]] = []
        if judge_mode == "live" and configured_specs:
            options.append(("configured", "設定ファイルのJudge 1〜3を使う"))
            options.append(("manual", "Judge 1〜3をこの画面で選び直す"))
            options.append(("mock", "mock Judgeで試す（APIキー不要）"))
        else:
            options.append(("mock", "mock Judgeで試す（APIキー不要）"))
            if configured_specs:
                options.append(("configured", "設定ファイルのJudge 1〜3を使う"))
            options.append(("manual", "Judge 1〜3をこの画面で選ぶ"))

        print("\n選択:")
        for index, (_, label) in enumerate(options, 1):
            print(f"  {index}. {label}")

        action = options[_prompt_index("番号", len(options)) - 1][0]
        if action == "mock":
            print("\n選択: mock Judge（APIキー不要）")
            return "mock", None
        if action == "manual":
            return "live", prompt_provider_specs()

        confirmed_specs = confirm_configured_provider_specs(configured_specs)
        if confirmed_specs:
            print("\n選択したJudge:")
            for judge_number, spec in enumerate(confirmed_specs, 1):
                print(f"  Judge {judge_number}: {format_provider_spec(spec)}")
            return "live", confirmed_specs
        print("\n少なくとも1つのJudgeが必要です。もう一度選んでください。")


def print_provider_key_summary(provider_specs: list[ProviderSpec]) -> None:
    print("\n設定済みの実LLM Judge候補:")
    for judge_number, spec in enumerate(provider_specs, 1):
        print(
            f"  Judge {judge_number}: {format_provider_spec(spec)} "
            f"[{_format_provider_key_state(spec.provider)}]"
        )


def _format_provider_key_state(provider: str) -> str:
    status = provider_key_status(provider)
    if status.ok:
        return f"key=set ({status.env_name})" if status.env_name else "key=not-required"
    env_name = status.env_name or "/".join(PROVIDER_KEY_ENVS.get(provider, ()))
    label = "key=missing" if status.state == "missing" else f"key={status.state}"
    return f"{label} ({env_name})" if env_name else label


def confirm_configured_provider_specs(provider_specs: list[ProviderSpec]) -> list[ProviderSpec]:
    confirmed_specs: list[ProviderSpec] = []
    for judge_number, spec in enumerate(provider_specs, 1):
        if _confirm_or_fix_provider_key(str(judge_number), spec):
            confirmed_specs.append(spec)
    return confirmed_specs


def prompt_user_cefr_level(system_level: str) -> str | None:
    print("\n=== ユーザーレベル確認 ===")
    print(f"SystemJudgeの判定: {system_level}")
    print("このファイルの正しいCEFRレベルを選んでください。")
    for index, level in enumerate(CEFR_LEVELS, 1):
        print(f"  {index}. {level}")
    skip_index = len(CEFR_LEVELS) + 1
    print(f"  {skip_index}. スキップ")

    while True:
        try:
            raw = input("番号: ").strip()
        except EOFError:
            return None
        try:
            selected = int(raw)
        except ValueError:
            print("数字で入力してください。")
            continue
        if 1 <= selected <= len(CEFR_LEVELS):
            return CEFR_LEVELS[selected - 1]
        if selected == skip_index:
            return None
        print(f"1〜{skip_index} の番号を入力してください。")


def apply_and_save_user_level_correction(
    *,
    profile: TuningProfile,
    profile_path: Path | None,
    record: dict,
    corrected_level: str,
) -> TuningProfile:
    updated_profile = apply_level_correction(
        profile,
        record=record,
        corrected_cefr=corrected_level,
        note="console final level feedback",
    )
    if profile_path:
        save_profile(updated_profile, profile_path)
    return updated_profile


def print_user_level_correction_summary(
    *,
    sample_id: str,
    previous_level: str,
    corrected_level: str,
    profile_path: Path | None,
    profile: TuningProfile,
) -> None:
    print("\n=== ユーザー補正 ===")
    print(f"ユーザー選択: {corrected_level}")
    print(f"SystemJudge: {previous_level}")
    print("判定過程を自動修正しました。")
    if profile_path:
        print(f"  - 保存先プロファイル: {profile_path}")
    else:
        print("  - 保存先プロファイル: 未指定のため、この実行内だけに反映")
    print(f"  - level_overrides[{sample_id}] = {corrected_level}")
    print(f"  - tuning_examples: {len(profile.tuning_examples)}件")
    transition = f"{previous_level}->{corrected_level}"
    correction_stats = profile.metadata.get("level_correction_stats", {})
    if isinstance(correction_stats, dict) and transition in correction_stats:
        print(f"  - level_correction_stats[{transition}] = {correction_stats[transition]}")
    print("  - 修正後の最終CEFRをユーザー選択レベルに更新")


def _build_review_record(
    *,
    audio_path: Path,
    review_sample_id: str,
    objective_data: dict,
    decision: AutoLevelDecision,
    raw_decision: AutoLevelDecision,
    auto_results: list[AutoLevelJudgeResult],
    judge_failures: list,
    override_applied: bool,
) -> dict:
    return {
        "sample_id": review_sample_id,
        "source_sample_id": audio_path.stem,
        "status": "ok",
        "audio_path": str(audio_path),
        "raw_predicted_cefr": raw_decision.final_cefr_level,
        "predicted_cefr": decision.final_cefr_level,
        "predicted_task_rating": _aggregate_auto_task_rating(auto_results),
        "profile_override_applied": override_applied,
        "needs_human_review": decision.needs_human_review or bool(judge_failures),
        "judge_results": [result.to_dict() for result in auto_results],
        "judge_failures": [
            {
                "judge_id": failure.judge_id,
                "provider": failure.provider_spec.provider,
                "model": failure.provider_spec.model,
                "message": failure.message,
            }
            for failure in judge_failures
        ],
        "objective_data": objective_data,
        "notes": "interactive judgement",
    }


def _aggregate_auto_task_rating(results: list[AutoLevelJudgeResult]) -> str:
    if not results:
        return ""
    counts: dict[str, int] = {}
    for result in results:
        counts[result.task_rating.value] = counts.get(result.task_rating.value, 0) + 1
    return sorted(counts.items(), key=lambda item: item[1], reverse=True)[0][0]


def list_audio_files(audio_dir: Path) -> list[Path]:
    if not audio_dir.exists():
        return []
    return sorted(
        path
        for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_EXTS
    )


def prompt_audio_choice(audio_files: list[Path]) -> Path:
    while True:
        print("\n音声ファイルを選択してください:")
        print("  1. ファイル選択ダイアログを開く")
        print("  2. パスを入力する（Finderからドラッグ&ドロップ可）")
        if audio_files:
            print("  3. サンプル音声から選ぶ（audio/）")

        choice = _prompt_index("番号", 3 if audio_files else 2)
        if choice == 1:
            selected = _choose_audio_with_dialog()
            if selected is not None:
                return selected
        elif choice == 2:
            selected = _prompt_audio_path()
            if selected is not None:
                return selected
        elif choice == 3 and audio_files:
            return _prompt_sample_audio_choice(audio_files)


def _prompt_sample_audio_choice(audio_files: list[Path]) -> Path:
    print("\nサンプル音声:")
    for index, path in enumerate(audio_files, 1):
        print(f"  {index}. {path.name}")
    selected_index = _prompt_index("番号", len(audio_files))
    return audio_files[selected_index - 1]


def _choose_audio_with_dialog() -> Path | None:
    script = 'POSIX path of (choose file with prompt "評価する音声ファイルを選択してください")'
    result = subprocess.run(
        ["osascript", "-e", script],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("ファイル選択がキャンセルされました。")
        return None
    return _validate_audio_path(Path(result.stdout.strip()))


def _prompt_audio_path() -> Path | None:
    raw = input("音声ファイルパス: ").strip()
    if not raw:
        print("パスが空です。")
        return None
    return _validate_audio_path(_normalize_audio_path_input(raw))


def _normalize_audio_path_input(raw: str) -> Path:
    parts = shlex.split(raw)
    text = parts[0] if parts else raw.strip()
    return Path(text).expanduser()


def _validate_audio_path(path: Path) -> Path | None:
    if not path.exists():
        print(f"ファイルが見つかりません: {path}")
        return None
    if not path.is_file():
        print(f"ファイルではありません: {path}")
        return None
    if path.suffix.lower() not in AUDIO_EXTS:
        print(f"対応していない形式です: {path.suffix}")
        print(f"対応形式: {', '.join(AUDIO_EXTS)}")
        return None
    return path


def prompt_provider_specs() -> list[ProviderSpec]:
    print("\nLLM Judgeを1〜3つ選択してください。")
    print("プロバイダは重複できません。Judge 2/3ではスキップできます。")
    print("キーは .env または環境変数から読みます。ここではキーを入力しません。")
    specs: list[ProviderSpec] = []
    used_providers: set[str] = set()
    for judge_number in ("1", "2", "3"):
        while True:
            spec = _prompt_provider_for_judge(
                judge_number,
                used_providers=used_providers,
                allow_skip=bool(specs),
            )
            if spec is not None or specs:
                break
            print("Judge 1は最低1つ必要です。別のプロバイダを選んでください。")
        if spec is None:
            break
        specs.append(spec)
        used_providers.add(spec.provider)
    print("\n選択したJudge:")
    for judge_number, spec in enumerate(specs, 1):
        print(f"  Judge {judge_number}: {format_provider_spec(spec)}")
    return specs


def _prompt_provider_for_judge(
    judge_id: str,
    *,
    used_providers: set[str],
    allow_skip: bool,
) -> ProviderSpec | None:
    providers = [
        provider
        for provider in PROVIDER_MODEL_OPTIONS
        if provider not in used_providers
    ]
    print(f"\nJudge {judge_id} のプロバイダ:")
    for index, provider in enumerate(providers, 1):
        env_label = "/".join(PROVIDER_KEY_ENVS[provider])
        print(f"  {index}. {provider} ({env_label})")
    if allow_skip:
        print(f"  {len(providers) + 1}. スキップして判定へ進む")
    selected = _prompt_index("番号", len(providers) + 1 if allow_skip else len(providers))
    if allow_skip and selected == len(providers) + 1:
        return None
    provider = providers[selected - 1]

    models = PROVIDER_MODEL_OPTIONS[provider]
    print(f"Judge {judge_id} のモデル:")
    for index, model in enumerate(models, 1):
        print(f"  {index}. {model}")
    print(f"  {len(models) + 1}. 手入力")
    selected = _prompt_index("番号", len(models) + 1)
    if selected <= len(models):
        model = models[selected - 1]
    else:
        model = _prompt_text("モデルID", default=models[0])
    spec = ProviderSpec(provider=provider, model=model)
    if not _confirm_or_fix_provider_key(judge_id, spec):
        return None
    return spec


def _confirm_or_fix_provider_key(judge_id: str, spec: ProviderSpec) -> bool:
    while True:
        status = provider_key_status(spec.provider)
        if status.ok:
            print(f"  -> {spec.provider}: key set ({status.env_name})")
            return True

        print(f"\n[キー確認] Judge {judge_id}: {format_provider_spec(spec)}")
        print(f"  {status.message}")
        print("  1. APIキーを入力して使う")
        print("  2. このJudgeをスキップ")
        choice = _prompt_index("番号", 2)
        if choice == 1:
            value = getpass(f"{status.env_name}: ").strip()
            if not value:
                print("キーが空です。")
                continue
            os.environ[status.env_name] = value
            _upsert_env_value(Path(".env"), status.env_name, value)
            print(f"  -> {spec.provider}: set ({status.env_name})")
            continue
        if choice == 2:
            print(f"  -> Judge {judge_id} をスキップします。")
            return False


def _upsert_env_value(path: Path, key: str, value: str) -> None:
    lines = []
    found = False
    if path.exists():
        lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = f"{key}={value}"
            found = True
            break
    if not found:
        if not lines:
            lines = [
                "# Local API keys for J-GRADE. This file is ignored by git.",
                "# Never commit real API keys.",
            ]
        lines.append(f"{key}={value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def print_objective_data(objective_data: dict) -> None:
    metrics = objective_data["fluency_metrics"]
    transcript = objective_data["raw_transcript_hiragana"]
    print("\n=== 客観データ ===")
    print(f"audio: {objective_data['audio_path']}")
    print(f"STT: {objective_data['stt_model']}")
    print(f"VAD: {objective_data['vad_model']}")
    print(f"ひらがな: {transcript[:240]}{'...' if len(transcript) > 240 else ''}")
    print(f"音声長: {metrics['audio_duration_sec']}秒")
    print(f"発話時間: {metrics['speech_sec']}秒 / 発話率: {metrics['speech_ratio_pct']}%")
    print(f"ポーズ: {metrics['pause_count']}回 / 平均 {metrics['avg_pause_sec']}秒 / 最長 {metrics['max_pause_sec']}秒")
    print(f"モーラ: {metrics['mora_count']} / {metrics['mora_per_sec']} モーラ/秒")
    print(f"流暢さグレード: {metrics['fluency_grade']}")
    if objective_data["top_pauses"]:
        print("長いポーズ:")
        for pause in objective_data["top_pauses"]:
            print(f"  {pause['start']}〜{pause['end']}秒 ({pause['duration']}秒)")


def print_judge_results(judge_results: list[JudgeResult]) -> None:
    print(f"\n=== {len(judge_results)} Judge結果 ===")
    for result in judge_results:
        print(
            f"Judge {result.judge_id} [{result.model_family}] "
            f"=> {result.rating.value} / confidence={result.confidence:.2f}"
        )
        if result.rationale:
            print(f"  理由: {result.rationale}")
        if result.evidence:
            print(f"  根拠: {' | '.join(result.evidence[:3])}")
        if result.risk_flags:
            print(f"  注意: {' | '.join(result.risk_flags)}")


def print_auto_level_judge_results(judge_results: list[AutoLevelJudgeResult]) -> None:
    print(f"\n=== {len(judge_results)} Judge CEFR推定 ===")
    for result in judge_results:
        print(
            f"Judge {result.judge_id} [{result.model_family}] "
            f"=> CEFR {result.predicted_cefr_level} / task={result.task_rating.value} "
            f"/ confidence={result.confidence:.2f}"
        )
        if result.rationale:
            print(f"  理由: {result.rationale}")
        if result.evidence:
            print(f"  根拠: {' | '.join(result.evidence[:3])}")
        if result.risk_flags:
            print(f"  注意: {' | '.join(result.risk_flags)}")


def print_consensus(decision: RoleplayDecision) -> None:
    print("\n=== 多数決 ===")
    print(f"ロールプレイ評価: {decision.consensus_rating.value}")
    print(f"厳密な多数決: {'yes' if decision.has_strict_majority else 'no'}")
    print(f"人間確認フラグ: {'yes' if decision.needs_human_review else 'no'}")


def print_auto_cefr_consensus(decision: AutoLevelDecision) -> None:
    print("\n=== CEFR多数決 ===")
    print(f"最終CEFR推定: {decision.final_cefr_level}")
    print(f"厳密な多数決: {'yes' if decision.has_strict_majority else 'no'}")
    print(f"人間確認フラグ: {'yes' if decision.needs_human_review else 'no'}")


def print_console_final_result(
    *,
    objective_data: dict,
    decision: AutoLevelDecision,
    judge_results: list[AutoLevelJudgeResult],
    title: str = "最終結果",
) -> None:
    metrics = objective_data["fluency_metrics"]
    transcript = objective_data["raw_transcript_hiragana"]
    task_rating = _aggregate_auto_task_rating(judge_results)
    confidence = _aggregate_auto_confidence(judge_results, decision.final_cefr_level)
    matching_results = [
        result
        for result in judge_results
        if result.predicted_cefr_level == decision.final_cefr_level
    ]
    rationale = (matching_results or judge_results)[0].rationale if judge_results else ""

    print(f"\n=== {title} ===")
    print(f"CEFRレベル: {decision.final_cefr_level}")
    print(f"タスク達成度: {task_rating or 'n/a'}")
    print(f"信頼度: {confidence:.2f}")
    print(f"人間確認: {'必要' if decision.needs_human_review else '不要'}")
    if rationale:
        print(f"理由: {rationale}")
    print("根拠:")
    print(f"  - ひらがなTranscript: {len(transcript)}文字")
    print(
        "  - 流暢性: "
        f"発話率 {metrics['speech_ratio_pct']}%, "
        f"{metrics['mora_per_sec']} モーラ/秒, "
        f"最長ポーズ {metrics['max_pause_sec']}秒"
    )
    print(
        "  - Judge: "
        + ", ".join(
            f"{result.judge_id}={result.predicted_cefr_level}"
            for result in judge_results
        )
    )


def _aggregate_auto_confidence(
    results: list[AutoLevelJudgeResult],
    final_level: str,
) -> float:
    matching = [
        result.confidence
        for result in results
        if result.predicted_cefr_level == final_level
    ]
    values = matching or [result.confidence for result in results]
    return round(sum(values) / len(values), 2) if values else 0.0


def _prompt_text(label: str, *, default: str) -> str:
    raw = input(f"{label} [{default}]: ").strip()
    return raw or default


def _prompt_index(label: str, max_index: int) -> int:
    while True:
        raw = input(f"{label}: ").strip()
        try:
            selected = int(raw)
        except ValueError:
            print("数字で入力してください。")
            continue
        if 1 <= selected <= max_index:
            return selected
        print(f"1〜{max_index} の番号を入力してください。")


def _ensure_live_keys_available(provider_specs: list[ProviderSpec]) -> None:
    missing = missing_key_envs(provider_specs)
    if not missing:
        return
    print("\nAPIキーが未設定です:")
    for env_name in missing:
        print(f"  - {env_name}")
    print("\n設定方法:")
    print("  .venv/bin/python -m jgrade_eval configure-keys")
    print("または `.env` に必要なキーを設定してください。")
    raise SystemExit(2)
