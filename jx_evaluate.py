"""
JFスタンダード スピーキング評価パイプライン（ローカルLLM版）

使い方:
  python jx_evaluate.py audio.mp3              # 音声ファイルから評価
  python jx_evaluate.py --text "にほんごがすきです"  # テキスト直接評価
  python jx_evaluate.py audio.mp3 --save result.json --verbose
  python jx_evaluate.py --demo                 # サンプル発話でデモ

前提:
  - LMスタジオが起動・Running状態であること
  - Developerタブでチャットモデルがロードされていること

パイプライン:
  [音声ファイル] → HiraganaTranscriber → ひらがなテキスト ─┐
  [テキスト直接]                                          ─┤
                                                         ↓
                                         Pass1: CoT分析（評価観点ごとの思考）
                                                         ↓
                                         Pass2: JSON出力（評価シート形式）

出力JSON例:
  {
    "level": "B1",
    "reason": "日常的な話題について要点を伝えられているが、複雑な表現には限界がある。",
    "checklist": {
      "課題達成": {"score": "○", "comment": "..."},
      ...
    },
    "strengths": ["接続詞を使って文をつなげられている"],
    "weaknesses": ["語彙の多様性がやや限られる"],
    "next_level_hints": ["B2に向けて：抽象的な話題でも意見を述べる練習を"],
    "confidence": 0.75
  }
"""

import sys
import json
import re
import argparse
import time
from pathlib import Path

from openai import OpenAI

from jx_criteria import (
    GLOBAL_SCALE, CAN_DO, CHECKLIST, LEVELS, SAMPLE_UTTERANCES
)

client = OpenAI(base_url="http://localhost:1234/v1", api_key="lm-studio")


# ─────────────────────────────────────────────────────────────
# プロンプト構築
# ─────────────────────────────────────────────────────────────

def _build_criteria_block() -> str:
    """評価基準テキストブロックを生成（LLMのシステムプロンプトに挿入）"""
    lines = ["【JFスタンダード スピーキング評価基準（CEFR準拠）】\n"]
    for level in LEVELS:
        lines.append(f"■ {level}：{GLOBAL_SCALE[level]}")
        lines.append("  ◇ 産出（話す）でできること：")
        for cd in CAN_DO[level]["産出"]:
            lines.append(f"    ・{cd}")
        lines.append("  ◇ やりとり（会話）でできること：")
        for cd in CAN_DO[level]["やりとり"]:
            lines.append(f"    ・{cd}")
        lines.append("")
    return "\n".join(lines)


def _build_checklist_block() -> str:
    """評価チェックシートテキストブロックを生成"""
    lines = [
        "【評価チェックシート（判定基準）】",
        "判定記号: ◎=十分達成（そのレベル以上の可能性あり） ○=何とか達成 △=達成できたとは言えない\n",
    ]
    for category, level_descs in CHECKLIST.items():
        lines.append(f"■ {category}")
        for level in LEVELS:
            lines.append(f"  {level}：{level_descs[level]}")
        lines.append("")
    return "\n".join(lines)


_CRITERIA_BLOCK = _build_criteria_block()
_CHECKLIST_BLOCK = _build_checklist_block()

# Pass 1: CoT分析のシステムプロンプト
_ANALYSIS_SYSTEM = f"""あなたはJFスタンダード（CEFR準拠）に基づく日本語スピーキング評価の専門家です。

{_CRITERIA_BLOCK}

{_CHECKLIST_BLOCK}

発話テキストを受け取ったら、以下の6観点それぞれについて分析してください。

【分析する6観点】
1. 課題達成：何を・どのくらい伝えられているか
2. 語彙・表現：語彙の豊富さ・適切さ・多様性
3. 文法・正確さ：文型の複雑さ・正確さ・一貫性
4. 流暢さ・一貫性：発話の流れ・まとまり・速度感
5. 発音・理解しやすさ：テキストから推定できる明瞭さ
6. 社会言語・語用論：場面適切性・丁寧さ・スタイルの使い分け

各観点で「◎/○/△」を判定し、その根拠を具体的に述べてください。
最後に、総合的なレベル（A1〜C2）を判定し、理由をまとめてください。

※入力テキストはひらがな音声認識の結果です。漢字表記は失われていますが、
  発話内容・語彙・文構造・流暢さのパターンから評価を行ってください。"""

# Pass 2: JSON抽出のシステムプロンプト
_JSON_SYSTEM = """あなたはJFスタンダード評価の専門家です。
提供された評価分析に基づいて、以下のJSON形式のみで最終評価を出力してください。
```json```マークや余分な説明は不要です。JSONのみを出力してください。

{
  "level": "A1またはA2またはB1またはB2またはC1またはC2",
  "reason": "判定理由（2〜3文で。具体的な根拠を含めること）",
  "checklist": {
    "課題達成": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"},
    "語彙・表現": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"},
    "文法・正確さ": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"},
    "流暢さ・一貫性": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"},
    "発音・理解しやすさ": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"},
    "社会言語・語用論": {"score": "◎または○または△", "comment": "具体的な根拠（1文）"}
  },
  "strengths": ["良い点1（具体的に）", "良い点2（具体的に）"],
  "weaknesses": ["改善点1（具体的に）", "改善点2（具体的に）"],
  "next_level_hints": ["次のレベルに向けたアドバイス1", "アドバイス2"],
  "confidence": 0.0から1.0の数値（判定の確信度）
}"""


# ─────────────────────────────────────────────────────────────
# コア関数
# ─────────────────────────────────────────────────────────────

def get_model(model: str | None = None) -> str:
    if model:
        return model
    models = client.models.list()
    available = [m.id for m in models.data if "embed" not in m.id.lower()]
    if not available:
        raise RuntimeError(
            "チャット用モデルがロードされていません。\n"
            "LMスタジオのDeveloperタブで「+ Load Model」をクリックしてください。"
        )
    return available[0]


def transcribe(audio_path: str) -> str:
    """音声ファイルをひらがなテキストに変換する"""
    from transcriber_a import HiraganaTranscriber
    print(f"  音声認識中: {audio_path}", file=sys.stderr)
    t0 = time.perf_counter()
    tr = HiraganaTranscriber()
    text = tr.transcribe(audio_path)
    print(f"  → 完了 ({time.perf_counter() - t0:.1f}秒): 「{text}」", file=sys.stderr)
    return text


def evaluate(utterance: str, model: str = None, verbose: bool = False) -> dict:
    """
    発話テキストをJFスタンダードで評価してJSONで返す。

    2パス構成:
      Pass 1: CoT分析（評価観点ごとの思考プロセス）
      Pass 2: JSON抽出（評価シート形式の構造化出力）

    Args:
        utterance: 評価する発話テキスト（ひらがな or 通常テキスト）
        model: LMスタジオのモデルID（Noneの場合は自動取得）
        verbose: CoT分析をstderrに表示するか

    Returns:
        評価結果dict（level, reason, checklist, strengths, weaknesses, ...）
    """
    model = get_model(model)

    # ── Pass 1: Chain-of-Thought 分析 ──────────────────────────
    if verbose:
        print("\n[Pass 1] 評価観点ごとに分析中...", file=sys.stderr)

    analysis_resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _ANALYSIS_SYSTEM},
            {
                "role": "user",
                "content": (
                    "以下の発話を評価してください。\n"
                    "※ひらがな音声認識テキストです。\n\n"
                    f"発話：「{utterance}」"
                ),
            },
        ],
        temperature=0.2,
        max_tokens=1200,
    )
    analysis = analysis_resp.choices[0].message.content.strip()

    if verbose:
        print("\n── CoT分析結果 ─────────────────────────────────────", file=sys.stderr)
        print(analysis, file=sys.stderr)
        print("────────────────────────────────────────────────────\n", file=sys.stderr)

    # ── Pass 2: JSON 抽出 ──────────────────────────────────────
    if verbose:
        print("[Pass 2] JSON評価シート生成中...", file=sys.stderr)

    json_resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _JSON_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"発話：「{utterance}」\n\n"
                    f"評価分析：\n{analysis}\n\n"
                    "上記の分析に基づいて、JSONを出力してください。"
                ),
            },
        ],
        temperature=0.1,
        max_tokens=900,
    )
    raw = json_resp.choices[0].message.content.strip()

    # JSON部分だけ抽出（モデルが余分なテキストを出した場合の保険）
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(
            f"JSON形式で返ってきませんでした。\n"
            f"生の出力:\n{raw}"
        )

    result = json.loads(match.group())
    result["utterance"] = utterance
    result["model"] = model
    result["cot_analysis"] = analysis
    return result


# ─────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────

def _run_demo(model: str):
    """サンプル発話を使ってデモ評価を実行する"""
    print("=" * 60)
    print("  JFスタンダード評価ツール デモモード")
    print("=" * 60)
    for level in LEVELS:
        utterance = SAMPLE_UTTERANCES[level][0]
        print(f"\n▶ サンプル（期待レベル: {level}）")
        print(f"  発話: 「{utterance[:50]}...」" if len(utterance) > 50 else f"  発話: 「{utterance}」")
        try:
            result = evaluate(utterance, model=model)
            print(f"  判定: {result['level']} | 確信度: {result['confidence']}")
            print(f"  理由: {result['reason']}")
            ok = "✓" if result["level"] == level else "✗"
            print(f"  結果: {ok} (期待:{level} / 判定:{result['level']})")
        except Exception as e:
            print(f"  エラー: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="JFスタンダード スピーキング評価（ローカルLLM）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python jx_evaluate.py audio.mp3
  python jx_evaluate.py --text "にほんごをべんきょうしています"
  python jx_evaluate.py audio.mp3 --save result.json --verbose
  python jx_evaluate.py --demo
        """,
    )
    parser.add_argument(
        "audio", nargs="?",
        help="音声ファイルパス（.mp3/.wav/.m4a など）"
    )
    parser.add_argument(
        "--text", "-t",
        help="評価する発話テキスト（音声なしで直接指定）"
    )
    parser.add_argument(
        "--save", "-s", metavar="FILE",
        help="JSON結果を保存するファイルパス"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="CoT分析を表示する"
    )
    parser.add_argument(
        "--model", "-m",
        help="使用するモデルID（未指定: LMスタジオ自動検出）"
    )
    parser.add_argument(
        "--demo", action="store_true",
        help="サンプル発話で全レベルのデモ評価を実行"
    )
    args = parser.parse_args()

    if not any([args.audio, args.text, args.demo]):
        parser.print_help()
        sys.exit(1)

    # LMスタジオ接続確認
    try:
        model = get_model(args.model)
        print(f"使用モデル: {model}", file=sys.stderr)
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        sys.exit(1)

    # デモモード
    if args.demo:
        _run_demo(model)
        return

    # 発話テキストの取得
    utterance = args.text
    if args.audio:
        if not Path(args.audio).exists():
            print(f"エラー: ファイルが見つかりません: {args.audio}", file=sys.stderr)
            sys.exit(1)
        utterance = transcribe(args.audio)
        print(f"\n文字起こし結果: 「{utterance}」\n", file=sys.stderr)

    # 評価実行
    print("評価中...", file=sys.stderr)
    t0 = time.perf_counter()
    result = evaluate(utterance, model=model, verbose=args.verbose)
    elapsed = time.perf_counter() - t0

    # 出力
    output = json.dumps(result, ensure_ascii=False, indent=2)
    print(output)
    print(f"\n完了 ({elapsed:.1f}秒)", file=sys.stderr)

    if args.save:
        Path(args.save).write_text(output, encoding="utf-8")
        print(f"保存完了: {args.save}", file=sys.stderr)


if __name__ == "__main__":
    main()
