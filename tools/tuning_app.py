from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jgrade_eval.live_judges import PROVIDER_MODEL_OPTIONS, ProviderSpec, load_env_file
from jgrade_eval.models import CEFR_LEVELS
from jgrade_eval.tuning_profile import (
    TuningProfile,
    apply_level_correction,
    load_profile,
    restore_history,
    save_profile,
)
from jgrade_eval.tuning_runner import run_tuning_dataset
from jgrade_eval.tuning_samples import (
    DEFAULT_REVIEW_DATASET_PATH,
    load_review_dataset,
    merge_run_result,
)
from jgrade_eval.tuning_store import read_json, write_json


def main() -> None:
    args = _parse_args()
    load_env_file(args.env_file)

    st.set_page_config(page_title="J-GRADE Tuning", layout="wide")
    st.title("J-GRADE Tuning Workbench")

    dataset_path = Path(st.sidebar.text_input("Review dataset", str(args.dataset)))
    profile_path = Path(st.sidebar.text_input("Profile path", str(args.profile)))
    output_path = Path(st.sidebar.text_input("Run output", str(args.output)))
    base_dir = Path(st.sidebar.text_input("Base dir", str(args.base_dir)))
    timeout_sec = st.sidebar.number_input("LLM timeout sec", min_value=5, max_value=300, value=60)

    dataset = _load_dataset(dataset_path)
    profile = load_profile(profile_path)
    edited_profile = _profile_controls(profile)

    result = st.session_state.get("latest_result") or _load_result(output_path)
    if _should_seed_from_result(dataset_path, dataset, result):
        dataset = merge_run_result(dataset_path, result, source="existing_output")

    if st.sidebar.button("Run benchmark", type="primary", width="stretch"):
        if not dataset or not dataset.get("items"):
            st.sidebar.error("Review samples are required.")
        else:
            with st.spinner("Running objective extraction and Judge evaluation..."):
                result = run_tuning_dataset(
                    dataset,
                    edited_profile,
                    base_dir=base_dir,
                    timeout_sec=float(timeout_sec),
                )
            write_json(output_path, result)
            merge_run_result(dataset_path, result, source="tuning_app")
            st.session_state["latest_result"] = result
            st.sidebar.success(f"wrote {output_path} and updated {dataset_path}")

    tab_dataset, tab_review, tab_metrics, tab_export = st.tabs(
        ["Review Samples", "CEFR Tuning", "Metrics", "Export"]
    )
    with tab_dataset:
        _dataset_tab(dataset)
    with tab_review:
        _review_tab(dataset_path, dataset, result, profile_path, edited_profile)
    with tab_metrics:
        _metrics_tab(result)
    with tab_export:
        _export_tab(profile_path, output_path, edited_profile, result)


def _profile_controls(profile: TuningProfile) -> TuningProfile:
    st.sidebar.divider()
    st.sidebar.subheader("Judge runtime")
    judge_mode = st.sidebar.selectbox(
        "Judge mode",
        ["mock", "live"],
        index=0 if profile.judge_mode == "mock" else 1,
    )
    allow_partial = st.sidebar.checkbox("Allow partial judges", profile.allow_partial_judges)

    providers: list[ProviderSpec] = []
    used: set[str] = set()
    for index in range(3):
        label = f"Judge {chr(ord('A') + index)}"
        provider_options = ["skip"] + [
            provider for provider in PROVIDER_MODEL_OPTIONS if provider not in used
        ]
        current = (
            profile.judge_providers[index].provider
            if index < len(profile.judge_providers)
            else "skip"
        )
        if current not in provider_options:
            current = "skip"
        provider = st.sidebar.selectbox(
            f"{label} provider",
            provider_options,
            index=provider_options.index(current),
            key=f"profile_provider_{index}",
        )
        if provider == "skip":
            continue
        used.add(provider)
        model_options = PROVIDER_MODEL_OPTIONS[provider]
        current_model = (
            profile.judge_providers[index].model
            if index < len(profile.judge_providers)
            and profile.judge_providers[index].provider == provider
            else model_options[0]
        )
        model = st.sidebar.text_input(
            f"{label} model",
            current_model,
            key=f"profile_model_{index}",
        )
        providers.append(ProviderSpec(provider=provider, model=model))

    return TuningProfile(
        name=profile.name,
        judge_mode=judge_mode,
        judge_providers=tuple(providers),
        allow_partial_judges=allow_partial,
        auto_cefr_system_prompt=profile.auto_cefr_system_prompt,
        level_overrides=profile.level_overrides,
        tuning_examples=profile.tuning_examples,
        change_history=profile.change_history,
        notes=profile.notes,
        metadata=profile.metadata,
    )


def _dataset_tab(dataset: dict | None) -> None:
    st.subheader("Review Samples")
    if not dataset:
        st.info("Run the CLI once, or run a benchmark, to accumulate reviewed samples.")
        return
    items = dataset.get("items", [])
    st.metric("Samples", len(items))
    df = pd.DataFrame([_dataset_row(item) for item in items])
    if not df.empty and "human_cefr" in df:
        st.bar_chart(df["human_cefr"].value_counts().reindex(CEFR_LEVELS, fill_value=0))
    st.dataframe(df, width="stretch", hide_index=True)


def _review_tab(
    dataset_path: Path,
    dataset: dict | None,
    result: dict | None,
    profile_path: Path,
    profile: TuningProfile,
) -> None:
    st.subheader("CEFR Tuning")
    records = _review_records(dataset, result)
    if not records:
        st.info("No judged samples yet. Run the CLI or benchmark first.")
        return
    selected_id = st.selectbox("Sample", [record["sample_id"] for record in records])
    record = next(record for record in records if record["sample_id"] == selected_id)

    cols = st.columns(4)
    cols[0].metric("Corrected CEFR", record.get("human_cefr") or "-")
    cols[1].metric("AI CEFR", record.get("predicted_cefr") or "-")
    cols[2].metric("Task", record.get("predicted_task_rating") or "-")
    cols[3].metric("Status", record.get("status", "-"))

    audio_path = record.get("audio_path")
    if audio_path and Path(audio_path).exists():
        st.audio(audio_path)

    objective = record.get("objective_data") or {}
    st.markdown("**Objective Data**")
    st.text_area(
        "Raw hiragana",
        objective.get("raw_transcript_hiragana", ""),
        height=120,
        disabled=True,
    )
    metrics = objective.get("fluency_metrics", {})
    if metrics:
        st.json(metrics)

    st.markdown("**Judge Results**")
    for judge in record.get("judge_results", []):
        st.write(
            f"{judge['judge_id']} / {judge['model_family']}: "
            f"{judge['predicted_cefr_level']} ({judge['task_rating']})"
        )
        st.caption(judge.get("rationale", ""))

    if record.get("judge_failures"):
        st.warning("Provider failures")
        st.json(record["judge_failures"])
    if record.get("error"):
        st.error(record["error"])

    st.markdown("**CEFR Correction**")
    default_level = record.get("human_cefr") or record.get("predicted_cefr") or CEFR_LEVELS[0]
    corrected = st.selectbox(
        "Corrected CEFR",
        CEFR_LEVELS,
        index=CEFR_LEVELS.index(default_level) if default_level in CEFR_LEVELS else 0,
        key=f"corrected_cefr_{record['sample_id']}",
    )
    if st.button("Apply CEFR correction", type="primary"):
        record["human_cefr"] = corrected
        tuned = apply_level_correction(
            profile,
            record=record,
            corrected_cefr=corrected,
            note=f"CEFR corrected in tuning app at {record['sample_id']}",
        )
        save_profile(tuned, profile_path)
        _save_corrected_cefr(dataset_path, dataset, record["sample_id"], corrected)
        st.success(
            f"Applied {record['sample_id']} -> {corrected}. "
            "Next runs will use the exact override, correction statistics, and prompt examples."
        )
        st.rerun()


def _metrics_tab(result: dict | None) -> None:
    st.subheader("Metrics")
    if not result:
        st.info("Run a benchmark to see metrics.")
        return
    metrics = result.get("metrics", {})
    cols = st.columns(4)
    cols[0].metric("Accuracy", f"{metrics.get('accuracy', 0):.3f}")
    cols[1].metric("Adjacent Acc.", f"{metrics.get('adjacent_accuracy', 0):.3f}")
    cols[2].metric("Macro F1", f"{metrics.get('macro_f1', 0):.3f}")
    cols[3].metric("Human Review", f"{metrics.get('human_review_rate', 0):.3f}")

    matrix = metrics.get("confusion_matrix", [])
    labels = metrics.get("labels", CEFR_LEVELS)
    if matrix:
        st.markdown("**Confusion Matrix**")
        st.dataframe(
            pd.DataFrame(matrix, index=[f"human_{x}" for x in labels], columns=labels),
            width="stretch",
        )
    mismatches = metrics.get("mismatched_samples", [])
    if mismatches:
        st.markdown("**Mismatched Samples**")
        st.write(", ".join(mismatches))


def _export_tab(
    profile_path: Path,
    output_path: Path,
    profile: TuningProfile,
    result: dict | None,
) -> None:
    st.subheader("Export")
    st.write("Profile:", str(profile_path))
    st.write("Latest run:", str(output_path))
    st.download_button(
        "Download profile JSON",
        data=_json_text(profile.to_dict()),
        file_name=f"{profile.name}.json",
        mime="application/json",
    )
    if result:
        st.download_button(
            "Download run JSON",
            data=_json_text(result),
            file_name=f"{result.get('run_id', 'tuning_run')}.json",
            mime="application/json",
        )
    if profile.tuning_examples:
        st.markdown("**CEFR tuning examples**")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "created_at": item.get("created_at"),
                        "sample_id": item.get("sample_id"),
                        "previous": item.get("previous_predicted_cefr"),
                        "corrected": item.get("corrected_cefr"),
                    }
                    for item in profile.tuning_examples
                ]
            ),
            width="stretch",
            hide_index=True,
        )

    st.markdown("**Recent profile changes**")
    if not profile.change_history:
        st.info("No saved history yet.")
        return
    history_rows = [
        {
            "index": index,
            "changed_at": item.get("changed_at"),
            "summary": item.get("summary"),
        }
        for index, item in enumerate(profile.change_history)
    ]
    st.dataframe(pd.DataFrame(history_rows), width="stretch", hide_index=True)
    selected = st.selectbox(
        "Rollback target",
        list(range(len(profile.change_history))),
        format_func=lambda index: (
            f"{profile.change_history[index].get('changed_at')} - "
            f"{profile.change_history[index].get('summary')}"
        ),
    )
    if st.button("Rollback profile to selected history"):
        restored = restore_history(profile, selected)
        save_profile(restored, profile_path)
        st.success("Profile rolled back. Re-run benchmark to use restored settings.")
        st.rerun()


def _load_dataset(path: Path) -> dict | None:
    if not str(path):
        return None
    return load_review_dataset(path)


def _review_records(dataset: dict | None, result: dict | None) -> list[dict]:
    if result and result.get("records"):
        return result["records"]
    if not dataset:
        return []
    return [_item_to_record(item) for item in dataset.get("items", [])]


def _item_to_record(item: dict) -> dict:
    prediction = item.get("last_prediction") or {}
    return {
        "sample_id": item.get("sample_id"),
        "status": prediction.get("status") or "ok",
        "audio_path": item.get("audio_path", ""),
        "human_cefr": item.get("human_cefr"),
        "human_rating": item.get("human_rating"),
        "raw_predicted_cefr": prediction.get("raw_predicted_cefr"),
        "predicted_cefr": prediction.get("predicted_cefr"),
        "predicted_task_rating": prediction.get("predicted_task_rating"),
        "calibration_applied": prediction.get("calibration_applied", False),
        "deliberation": prediction.get("deliberation", {}),
        "needs_human_review": prediction.get("needs_human_review", False),
        "judge_results": prediction.get("judge_results", []),
        "judge_failures": prediction.get("judge_failures", []),
        "error": prediction.get("error", ""),
        "objective_data": item.get("objective_data", {}),
        "notes": item.get("notes", ""),
    }


def _dataset_row(item: dict) -> dict:
    prediction = item.get("last_prediction") or {}
    return {
        "sample_id": item.get("sample_id"),
        "audio_path": item.get("audio_path"),
        "human_cefr": item.get("human_cefr"),
        "ai_cefr": prediction.get("predicted_cefr"),
        "raw_ai_cefr": prediction.get("raw_predicted_cefr"),
        "status": prediction.get("status"),
        "recorded_at": prediction.get("recorded_at"),
        "source": prediction.get("source"),
        "notes": item.get("notes"),
    }


def _save_corrected_cefr(
    dataset_path: Path,
    dataset: dict | None,
    sample_id: str,
    corrected: str,
) -> None:
    updated = dataset or load_review_dataset(dataset_path)
    for item in updated.get("items", []):
        if item.get("sample_id") == sample_id:
            item["human_cefr"] = corrected
            break
    updated["updated_at"] = _now_iso()
    write_json(dataset_path, updated)


def _should_seed_from_result(
    dataset_path: Path,
    dataset: dict | None,
    result: dict | None,
) -> bool:
    if not result or not result.get("records"):
        return False
    if dataset_path != DEFAULT_REVIEW_DATASET_PATH:
        return False
    return not dataset or not dataset.get("items")


def _load_result(path: Path) -> dict | None:
    if not str(path) or not path.exists():
        return None
    try:
        return read_json(path)
    except Exception:
        return None


def _json_text(payload: dict) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_REVIEW_DATASET_PATH)
    parser.add_argument("--profile", type=Path, default=Path("tuning_profiles/base.json"))
    parser.add_argument("--output", type=Path, default=Path("outputs/tuning_runs/latest.json"))
    parser.add_argument("--base-dir", type=Path, default=Path.cwd())
    parser.add_argument("--env-file", type=Path)
    return parser.parse_args()


if __name__ == "__main__":
    main()
