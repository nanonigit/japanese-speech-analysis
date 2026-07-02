from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jgrade_eval.models import CEFR_LEVELS, Rating
from jgrade_eval.tuning_store import write_json


AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".ogg"}


def build_dataset(labels_csv: Path, *, audio_dir: Path | None = None) -> dict[str, Any]:
    records = []
    with labels_csv.open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        for row_index, row in enumerate(reader, 1):
            audio_path = _resolve_audio_path(row, audio_dir)
            human_cefr = str(row.get("human_cefr", "")).strip().upper()
            if human_cefr and human_cefr not in CEFR_LEVELS:
                raise ValueError(f"row {row_index}: invalid human_cefr: {human_cefr}")
            human_rating = str(row.get("human_rating", "")).strip()
            if human_rating:
                Rating.parse(human_rating)
            sample_id = str(row.get("sample_id") or audio_path.stem).strip()
            records.append(
                {
                    "sample_id": sample_id,
                    "audio_path": str(audio_path),
                    "human_cefr": human_cefr,
                    "human_rating": human_rating,
                    "roleplay_id": str(row.get("roleplay_id") or "rp-1").strip(),
                    "roleplay_task": str(row.get("roleplay_task") or "不明").strip(),
                    "notes": str(row.get("notes") or "").strip(),
                }
            )
    return {"name": labels_csv.stem, "items": records}


def _resolve_audio_path(row: dict[str, str], audio_dir: Path | None) -> Path:
    raw_audio_path = str(row.get("audio_path") or "").strip()
    if not raw_audio_path:
        sample_id = str(row.get("sample_id") or "").strip()
        if not sample_id or audio_dir is None:
            raise ValueError("audio_path is required unless audio_dir and sample_id are provided.")
        matches = [
            path
            for path in audio_dir.iterdir()
            if path.is_file()
            and path.suffix.lower() in AUDIO_EXTS
            and path.stem == sample_id
        ]
        if not matches:
            raise FileNotFoundError(f"audio file not found for sample_id={sample_id}")
        return matches[0]

    path = Path(raw_audio_path).expanduser()
    if not path.is_absolute() and audio_dir is not None:
        path = audio_dir / path
    if not path.exists():
        raise FileNotFoundError(f"audio file not found: {path}")
    if path.suffix.lower() not in AUDIO_EXTS:
        raise ValueError(f"unsupported audio extension: {path.suffix}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a J-GRADE tuning manifest")
    parser.add_argument("--labels", required=True, type=Path, help="human label CSV")
    parser.add_argument("--audio-dir", type=Path, help="base directory for relative audio paths")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    dataset = build_dataset(args.labels, audio_dir=args.audio_dir)
    write_json(args.out, dataset)
    print(f"wrote {args.out} ({len(dataset['items'])} items)")


if __name__ == "__main__":
    main()
