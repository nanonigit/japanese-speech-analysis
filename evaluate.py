"""
J-GRADE 発話レベル評価スクリプト（ローカルLLM版）

使い方:
  python evaluate.py "にほんごがすきです"
  python evaluate.py  （インタラクティブモード）

前提:
  - LMスタジオが起動していること
  - DeveloperタブでサーバーがRunning状態であること
  - チャット用モデルがロードされていること

出力例:
  {
    "level": "A2",
    "reason": "短い文を正確に発話できている。語彙・文法は基礎レベル。",
    "strengths": ["基本的な文構造が使えている"],
    "weaknesses": ["語彙が限定的"],
    "confidence": 0.85
  }
"""

import sys
import json
import re
from openai import OpenAI

# LMスタジオのローカルAPIに接続（インターネット不要）
client = OpenAI(
    base_url="http://localhost:1234/v1",
    api_key="lm-studio",  # LMスタジオはキー不要だが形式上必要
)

# JFスタンダード（CEFR準拠）の評価基準
JF_CRITERIA = """
【JFスタンダード スピーキング評価基準】

A1: 極めて限られた表現のみ。暗記した短いフレーズ・挨拶など。
    例: 「はじめまして」「ありがとう」「これはなんですか」

A2: 身近な話題について短い発話が可能。基本的な文型を使える。
    例: 「わたしはがくせいです」「まいにちがっこうへいきます」

B1: 日常的な話題・自分の専門分野について要点を伝えられる。
    接続詞を使い、ある程度まとまった発話ができる。
    例: 「〜ので、〜と思います」「〜したことがあります」

B2: 幅広い話題について明確に意見を述べられる。
    具体的な説明・理由付けができ、スムーズに話せる。

C1: 複雑な内容を論理的・流暢に話せる。
    自然な表現・慣用句も使える。言い淀みが少ない。

C2: ネイティブに近い流暢さ。あらゆる場面で的確に表現できる。
"""

SYSTEM_PROMPT = f"""あなたはJFスタンダード（CEFR準拠）に基づく日本語スピーキング評価の専門家です。

{JF_CRITERIA}

ユーザーから日本語の発話テキストが与えられます。
以下のJSON形式のみで回答してください。余分な説明は不要です。

{{
  "level": "A1/A2/B1/B2/C1/C2のいずれか",
  "reason": "判定理由を1〜2文で",
  "strengths": ["良い点1", "良い点2"],
  "weaknesses": ["改善点1", "改善点2"],
  "confidence": 0.0〜1.0の数値
}}"""


def evaluate(utterance: str, model: str = None) -> dict:
    """発話テキストをJFスタンダードで評価してJSONで返す"""

    # モデル未指定の場合はLMスタジオで現在ロード中のモデルを自動取得
    if model is None:
        models = client.models.list()
        available = [m.id for m in models.data if "embed" not in m.id.lower()]
        if not available:
            raise RuntimeError(
                "チャット用モデルがロードされていません。\n"
                "LMスタジオのDeveloperタブで「+ Load Model」をクリックしてください。"
            )
        model = available[0]

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"以下の発話を評価してください：\n\n「{utterance}」"},
    ]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0.1,  # 低めにして安定したJSON出力を狙う
        max_tokens=512,
    )

    raw = response.choices[0].message.content.strip()

    # JSON部分だけ抽出（モデルが余分なテキストを出した場合の保険）
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError(f"JSON形式で返ってきませんでした。\n生の出力:\n{raw}")

    result = json.loads(match.group())
    result["model"] = model
    result["utterance"] = utterance
    return result


def main():
    if len(sys.argv) > 1:
        # コマンドライン引数から発話テキストを受け取る
        utterance = " ".join(sys.argv[1:])
        print(f"\n評価対象: 「{utterance}」\n")
        result = evaluate(utterance)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        # インタラクティブモード
        print("=" * 55)
        print("  J-GRADE 発話レベル評価ツール（ローカルLLM版）")
        print("  終了するには Ctrl+C")
        print("=" * 55)

        # 利用可能モデルの確認
        try:
            models = client.models.list()
            chat_models = [m.id for m in models.data if "embed" not in m.id.lower()]
            if chat_models:
                print(f"\n使用モデル: {chat_models[0]}")
            else:
                print("\n⚠️  チャット用モデルが見つかりません。")
                print("LMスタジオのDeveloperタブでモデルをロードしてください。")
                return
        except Exception as e:
            print(f"\n⚠️  LMスタジオに接続できません: {e}")
            print("LMスタジオを起動してサーバーをStartにしてください。")
            return

        # ダミーデータでのデモ
        demo_utterances = [
            "わたし は まいにち がっこう に いきます",
            "にほんご を べんきょう して います が むずかしい です",
            "しゅうまつ に ともだち と えいが を みて それから レストラン で しょくじ を しました",
        ]

        print("\n--- デモ評価（サンプル発話） ---")
        for utt in demo_utterances:
            print(f"\n▶ 発話: 「{utt}」")
            try:
                result = evaluate(utt)
                print(f"  レベル: {result['level']}")
                print(f"  理由  : {result['reason']}")
                print(f"  JSON  : {json.dumps(result, ensure_ascii=False)}")
            except Exception as e:
                print(f"  エラー: {e}")

        print("\n--- 自由入力モード ---")
        while True:
            try:
                utt = input("\n発話テキストを入力 > ").strip()
                if not utt:
                    continue
                result = evaluate(utt)
                print(json.dumps(result, ensure_ascii=False, indent=2))
            except KeyboardInterrupt:
                print("\n終了します。")
                break
            except Exception as e:
                print(f"エラー: {e}")


if __name__ == "__main__":
    main()
