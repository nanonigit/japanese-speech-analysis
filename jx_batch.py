"""
JFスタンダード 評価精度検証スクリプト

ラベル済みサンプルデータを使って評価精度を測定する。

使い方:
  python jx_batch.py samples.csv
  python jx_batch.py samples.csv --out report.json
  python jx_batch.py samples.csv --model "qwen2.5-72b"

CSVフォーマット（ヘッダー行必須）:
  text,expected           # テキストで評価する場合
  audio_path,expected     # 音声ファイルで評価する場合（拡張子で自動判別）

使用できる列名:
  入力: text / テキスト / 発話 / audio / 音声ファイル / audio_path
  ラベル: expected / 期待レベル / label / level

CSVサンプル:
  text,expected
  わたしはたなかです,A1
  まいにちかいしゃにいきます,A2
  しゅうまつにともだちとえいがをみました。とてもたのしかったです,B1

精度レポート出力例:
  総数         : 12
  完全一致     : 7 / 12 (58.3%)
  ±1レベル以内 : 11 / 12 (91.7%)
  混同行列（行=期待, 列=判定）
  ...
"""

import sys
import json
import csv
import argparse
import time
from collections import defaultdict
from pathlib import Path

from jx_evaluate import evaluate, transcribe, get_model
from jx_criteria import LEVELS

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac"}

LEVEL_ORDER = {lvl: i for i, lvl in enumerate(LEVELS)}


# ─────────────────────────────────────────────────────────────
# 精度計算
# ─────────────────────────────────────────────────────────────

def match_type(predicted: str, expected: str) -> str:
    """exact: 完全一致 / adjacent: ±1レベル / far: それ以上 / error: エラー"""
    if predicted == "ERROR":
        return "error"
    diff = abs(LEVEL_ORDER.get(predicted, -99) - LEVEL_ORDER.get(expected, -99))
    if diff == 0:
        return "exact"
    elif diff == 1:
        return "adjacent"
    else:
        return "far"


# ─────────────────────────────────────────────────────────────
# バッチ処理
# ─────────────────────────────────────────────────────────────

def run_batch(samples: list[dict], model: str) -> list[dict]:
    results = []
    total = len(samples)

    for i, sample in enumerate(samples, 1):
        text = sample["text"].strip()
        expected = sample["expected"].strip().upper()

        is_audio = (
            Path(text).suffix.lower() in AUDIO_EXTENSIONS
            and Path(text).exists()
        )

        label_icon = "🎤" if is_audio else "📝"
        preview = text[:40] + ("..." if len(text) > 40 else "")
        print(f"[{i:3d}/{total}] {label_icon} {preview}  (期待: {expected})", file=sys.stderr)

        t0 = time.perf_counter()
        try:
            utterance = transcribe(text) if is_audio else text
            result = evaluate(utterance, model=model)
            predicted = result.get("level", "?").strip().upper()
            mtype = match_type(predicted, expected)
            elapsed = time.perf_counter() - t0

            icon = "✓" if mtype == "exact" else "~" if mtype == "adjacent" else "✗"
            print(f"       {icon} 判定:{predicted}  ({mtype})  {elapsed:.1f}秒", file=sys.stderr)

            results.append({
                "input": text,
                "utterance": utterance,
                "expected": expected,
                "predicted": predicted,
                "match": mtype,
                "confidence": result.get("confidence"),
                "reason": result.get("reason"),
                "checklist": result.get("checklist"),
            })

        except Exception as e:
            elapsed = time.perf_counter() - t0
            print(f"       ✗ エラー: {e}  ({elapsed:.1f}秒)", file=sys.stderr)
            results.append({
                "input": text,
                "utterance": text,
                "expected": expected,
                "predicted": "ERROR",
                "match": "error",
                "error": str(e),
            })

    return results


# ─────────────────────────────────────────────────────────────
# レポート出力
# ─────────────────────────────────────────────────────────────

def print_report(results: list[dict]):
    total = len(results)
    if total == 0:
        print("結果がありません。", file=sys.stderr)
        return

    exact_n    = sum(1 for r in results if r["match"] == "exact")
    adjacent_n = sum(1 for r in results if r["match"] in ("exact", "adjacent"))
    errors_n   = sum(1 for r in results if r["match"] == "error")
    valid_n    = total - errors_n

    print("\n" + "=" * 60)
    print("  JFスタンダード評価 精度レポート")
    print("=" * 60)
    print(f"  総数              : {total}")
    if errors_n:
        print(f"  エラー            : {errors_n}（スキップ）")
    print(f"  完全一致          : {exact_n:3d} / {valid_n} ({exact_n/max(valid_n,1)*100:5.1f}%)")
    print(f"  ±1レベル以内      : {adjacent_n:3d} / {valid_n} ({adjacent_n/max(valid_n,1)*100:5.1f}%)")

    # 混同行列
    matrix = defaultdict(lambda: defaultdict(int))
    for r in results:
        if r["match"] != "error":
            matrix[r["expected"]][r["predicted"]] += 1

    print()
    print("  混同行列（行=期待レベル, 列=判定レベル）")
    col_w = 5
    header = "  " + " " * 5 + "".join(f"{lv:>{col_w}}" for lv in LEVELS)
    print(header)
    for exp in LEVELS:
        if not any(matrix[exp].values()):
            continue
        row = f"  {exp:4s} "
        for pred in LEVELS:
            n = matrix[exp][pred]
            cell = f"[{n}]" if exp == pred and n > 0 else str(n) if n > 0 else "."
            row += f"{cell:>{col_w}}"
        print(row)

    # チェックシート観点ごとの傾向
    score_totals: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in results:
        if r.get("checklist"):
            for cat, val in r["checklist"].items():
                score_totals[cat][val.get("score", "?")] += 1

    if score_totals:
        print()
        print("  評価観点ごとのスコア分布（全サンプル合計）")
        print(f"  {'観点':<18}  ◎   ○   △")
        print("  " + "-" * 38)
        for cat in [
            "課題達成", "語彙・表現", "文法・正確さ",
            "流暢さ・一貫性", "発音・理解しやすさ", "社会言語・語用論"
        ]:
            scores = score_totals.get(cat, {})
            maru2 = scores.get("◎", 0)
            maru  = scores.get("○", 0)
            tri   = scores.get("△", 0)
            print(f"  {cat:<18}  {maru2:2d}  {maru:2d}  {tri:2d}")

    # 詳細リスト
    print()
    print("  詳細結果")
    print("  " + "-" * 58)
    for r in results:
        icon = "✓" if r["match"] == "exact" else "~" if r["match"] == "adjacent" else "✗"
        utt_preview = str(r.get("utterance", r["input"]))
        utt_preview = utt_preview[:35] + ("..." if len(utt_preview) > 35 else "")
        conf = f"  conf:{r['confidence']:.2f}" if r.get("confidence") else ""
        print(f"  {icon} {r['expected']} → {r.get('predicted','?'):3s}{conf}  「{utt_preview}」")

    print()


# ─────────────────────────────────────────────────────────────
# CSV読み込みユーティリティ
# ─────────────────────────────────────────────────────────────

_TEXT_COLS     = {"text", "テキスト", "発話", "audio", "音声ファイル", "audio_path"}
_EXPECTED_COLS = {"expected", "期待レベル", "label", "level", "正解"}


def _load_csv(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return []

    keys = list(rows[0].keys())
    text_col = next((k for k in keys if k.strip() in _TEXT_COLS), keys[0])
    exp_col  = next((k for k in keys if k.strip() in _EXPECTED_COLS), keys[1] if len(keys) > 1 else None)

    if not exp_col:
        raise ValueError(
            f"CSVに期待レベル列が見つかりません。\n"
            f"使える列名: {', '.join(sorted(_EXPECTED_COLS))}\n"
            f"現在の列: {', '.join(keys)}"
        )

    return [{"text": r[text_col], "expected": r[exp_col]} for r in rows if r[text_col].strip()]


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="JFスタンダード 評価精度検証",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "csv_file",
        help="サンプルCSVファイルパス"
    )
    parser.add_argument(
        "--out", "-o", metavar="FILE",
        help="詳細結果をJSONで保存"
    )
    parser.add_argument(
        "--model", "-m",
        help="モデルID（未指定: LMスタジオ自動検出）"
    )
    args = parser.parse_args()

    if not Path(args.csv_file).exists():
        print(f"エラー: ファイルが見つかりません: {args.csv_file}", file=sys.stderr)
        sys.exit(1)

    try:
        samples = _load_csv(args.csv_file)
    except Exception as e:
        print(f"CSVの読み込みエラー: {e}", file=sys.stderr)
        sys.exit(1)

    if not samples:
        print("CSVにデータがありません。", file=sys.stderr)
        sys.exit(1)

    try:
        model = get_model(args.model)
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"モデル: {model}", file=sys.stderr)
    print(f"サンプル数: {len(samples)}", file=sys.stderr)
    print("-" * 60, file=sys.stderr)

    t_start = time.perf_counter()
    results = run_batch(samples, model)
    t_total = time.perf_counter() - t_start

    print_report(results)
    print(f"  合計処理時間: {t_total:.1f}秒  ({t_total/len(results):.1f}秒/件)\n")

    if args.out:
        Path(args.out).write_text(
            json.dumps(results, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        print(f"詳細結果保存: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
