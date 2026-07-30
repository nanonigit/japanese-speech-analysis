from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib import error, request

from .models import CEFR_LEVELS, Rating


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CATALOG_PATH = REPO_ROOT / "examples" / "jfs_roleplay_catalog.json"
DEFAULT_DOWNLOAD_DIR = Path("data/external/jfs_roleplay")
DEFAULT_TEST_AUDIO_DIR = Path("audio")
DEFAULT_TUNING_DATASET_PATH = Path("data/tuning/jfs_roleplay_dataset.json")

FetchBytes = Callable[[str], bytes]


@dataclass(frozen=True)
class DownloadedAsset:
    url: str
    path: Path
    bytes: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "path": str(self.path),
            "bytes": self.bytes,
            "status": self.status,
        }


def load_jfs_catalog(path: Path | None = None) -> dict[str, Any]:
    catalog_path = path or DEFAULT_CATALOG_PATH
    return json.loads(catalog_path.read_text(encoding="utf-8"))


def validate_jfs_catalog(catalog: dict[str, Any]) -> None:
    samples = catalog.get("samples", [])
    if not samples:
        raise ValueError("JFS catalog must contain at least one sample.")
    seen: set[str] = set()
    for sample in samples:
        sample_id = str(sample.get("sample_id", ""))
        if not sample_id:
            raise ValueError("JFS catalog sample is missing sample_id.")
        if sample_id in seen:
            raise ValueError(f"duplicate JFS catalog sample_id: {sample_id}")
        seen.add(sample_id)

        level = str(sample.get("human_cefr", "")).upper()
        if level not in CEFR_LEVELS:
            raise ValueError(f"{sample_id}: human_cefr must be one of {CEFR_LEVELS}.")
        Rating.parse(str(sample.get("human_rating", "")))
        _require_https(sample, "audio_url")
        _require_https(sample, "evaluation_pdf_url")


def download_jfs_assets(
    *,
    catalog_path: Path | None = None,
    output_dir: Path = DEFAULT_DOWNLOAD_DIR,
    audio_dir: Path = DEFAULT_TEST_AUDIO_DIR,
    include_pdfs: bool = True,
    force: bool = False,
    fetch_bytes: FetchBytes | None = None,
) -> dict[str, Any]:
    catalog = load_jfs_catalog(catalog_path)
    validate_jfs_catalog(catalog)
    fetch = fetch_bytes or _fetch_url_bytes

    docs_dir = output_dir / "docs"
    assets: list[DownloadedAsset] = []
    for sample in catalog["samples"]:
        assets.append(
            _download_one(
                url=str(sample["audio_url"]),
                path=audio_dir / str(sample["audio_filename"]),
                force=force,
                fetch_bytes=fetch,
            )
        )
        if include_pdfs:
            assets.append(
                _download_one(
                    url=str(sample["evaluation_pdf_url"]),
                    path=docs_dir / str(sample["evaluation_pdf_filename"]),
                    force=force,
                    fetch_bytes=fetch,
                )
            )

    return {
        "catalog_name": catalog.get("name", "official_jfs_roleplay_samples"),
        "source_page_url": catalog.get("source_page_url"),
        "site_policy_url": catalog.get("site_policy_url"),
        "license_note": catalog.get("license_note"),
        "output_dir": str(output_dir),
        "audio_dir": str(audio_dir),
        "sample_count": len(catalog["samples"]),
        "asset_count": len(assets),
        "downloaded_count": sum(asset.status == "downloaded" for asset in assets),
        "skipped_count": sum(asset.status == "exists" for asset in assets),
        "assets": [asset.to_dict() for asset in assets],
    }


def build_jfs_tuning_dataset(
    *,
    catalog_path: Path | None = None,
    audio_dir: Path = DEFAULT_TEST_AUDIO_DIR,
    require_audio: bool = True,
) -> dict[str, Any]:
    catalog = load_jfs_catalog(catalog_path)
    validate_jfs_catalog(catalog)

    items: list[dict[str, Any]] = []
    missing_audio: list[str] = []
    for sample in catalog["samples"]:
        audio_path = audio_dir / str(sample["audio_filename"])
        if not audio_path.exists():
            missing_audio.append(str(audio_path))
            continue
        items.append(
            {
                "sample_id": sample["sample_id"],
                "audio_path": str(audio_path),
                "human_cefr": sample["human_cefr"],
                "human_rating": sample["human_rating"],
                "roleplay_id": sample["task_id"],
                "roleplay_task": sample["roleplay_task"],
                "jfs_can_do_criteria": list(sample.get("jfs_can_do_criteria", [])),
                "notes": (
                    "Official JF Standard role-play sample. "
                    f"rating={sample['human_rating']}; "
                    f"source={sample['sample_page_url']}"
                ),
                "source_sample_id": sample["sample_id"],
                "source": {
                    "publisher": catalog.get("publisher"),
                    "source_page_url": catalog.get("source_page_url"),
                    "sample_page_url": sample.get("sample_page_url"),
                    "evaluation_pdf_url": sample.get("evaluation_pdf_url"),
                    "audio_url": sample.get("audio_url"),
                },
            }
        )

    if require_audio and missing_audio:
        raise FileNotFoundError(
            "missing JFS audio files; run download-jfs-samples first:\n"
            + "\n".join(missing_audio[:10])
        )

    return {
        "name": "official_jfs_roleplay_tuning_dataset",
        "source_catalog": str(catalog_path or DEFAULT_CATALOG_PATH),
        "source_page_url": catalog.get("source_page_url"),
        "site_policy_url": catalog.get("site_policy_url"),
        "license_note": catalog.get("license_note"),
        "coverage_note": catalog.get("coverage_note"),
        "level_counts": _level_counts(items),
        "missing_audio": missing_audio,
        "items": items,
    }


def _download_one(
    *,
    url: str,
    path: Path,
    force: bool,
    fetch_bytes: FetchBytes,
) -> DownloadedAsset:
    if path.exists() and path.stat().st_size > 0 and not force:
        return DownloadedAsset(url, path, path.stat().st_size, "exists")

    payload = fetch_bytes(url)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return DownloadedAsset(url, path, len(payload), "downloaded")


def _fetch_url_bytes(url: str) -> bytes:
    try:
        with request.urlopen(url, timeout=60) as response:
            return response.read()
    except error.URLError:
        # macOS framework Python installations can miss the system certificate
        # bundle. curl uses the platform trust store and still validates TLS.
        completed = subprocess.run(
            ["/usr/bin/curl", "-fsSL", url],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        return completed.stdout


def _require_https(sample: dict[str, Any], key: str) -> None:
    value = str(sample.get(key, ""))
    if not value.startswith("https://"):
        raise ValueError(f"{sample.get('sample_id', '<unknown>')}: {key} must use https.")


def _level_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts = {level: 0 for level in CEFR_LEVELS}
    for item in items:
        level = str(item.get("human_cefr", "")).upper()
        if level in counts:
            counts[level] += 1
    return {level: count for level, count in counts.items() if count}
