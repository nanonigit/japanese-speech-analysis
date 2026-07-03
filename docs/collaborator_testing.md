# J-GRADE Console Testing Guide

この手順は、協力者が自分の音声ファイルでCEFR推定を試し、結果を共有するためのものです。

## 1. 初回セットアップ

```bash
git clone --recurse-submodules https://github.com/goyojima-hash/japanese-speech-analysis.git
cd japanese-speech-analysis
uv sync --frozen
```

macOSでFinderから起動したい場合は、`run_jgrade_console.command` をダブルクリックします。Terminalから起動する場合は以下です。

```bash
./run_jgrade_console.command
```

## 2. Judge LLMの選び方

Judge設定は `config/judge_llms.json` にあります。コードは編集しません。

最初はAPIキーなしで動くように `judge_mode` が `mock` になっています。実LLMで試す場合は、`.env.example` を `.env` にコピーしてAPIキーを入れたうえで、`judge_mode` を `live` に変更してください。

```json
{
  "judge_mode": "live",
  "live_judges": [
    {
      "judge_id": "A",
      "enabled": true,
      "provider": "anthropic",
      "model": "claude-sonnet-4-6"
    },
    {
      "judge_id": "B",
      "enabled": true,
      "provider": "openai",
      "model": "gpt-5.4-mini"
    },
    {
      "judge_id": "C",
      "enabled": true,
      "provider": "gemini",
      "model": "gemini-3.1-pro-preview"
    }
  ]
}
```

有効にできるJudgeは1〜3つです。多数決の検証には3つを推奨します。プロバイダは重複できません。特定のJudgeを外したい場合は、その項目の `enabled` を `false` にします。

## 3. 音声の選び方

起動直後に `=== Judge設定 ===` が表示されます。ここで、以下から選びます。

- `mock Judgeで試す`: APIキーなしで疎通確認する
- `設定ファイルのJudge 1〜3を使う`: `config/judge_llms.json` の設定で実LLM評価する
- `Judge 1〜3をこの画面で選ぶ`: 起動時にprovider/modelを選び直す

実LLM Judge候補には `key=set`、`key=missing`、`key=invalid` のようにAPIキー状態が表示されます。APIキーの値そのものは表示されません。

起動後、以下から選べます。

- ファイル選択ダイアログ
- パス入力
- `audio/` に入っているサンプル音声

自分の音声をまとめて管理したい場合は、`audio/` に置いてから起動してください。公式JF音声など、配布できない音声ファイルはgitに追加しないでください。

## 4. 結果の見方

コンソール末尾の `=== 最終結果 ===` を見てください。ここが報告用の出口です。

```text
=== 最終結果 ===
CEFRレベル: B1
タスク達成度: ○
信頼度: 0.55
人間確認: 不要
理由: ...
根拠:
  - ひらがなTranscript: 382文字
  - 流暢性: 発話率 82.33%, 6.37 モーラ/秒, 最長ポーズ 0.8秒
  - Judge: A=B1, B=A2, C=B1
```

## 5. 報告テンプレート

```text
音声ファイル名:
音声の長さ:
話者メモ:
Judge設定:
最終CEFR:
タスク達成度:
信頼度:
Judgeごとの推定:
ひらがなTranscriptの印象:
流暢性指標の印象:
判定が妥当だと思うか:
気になった点:
```

APIキーや個人情報を含む `.env`、個人音声、配布不可の音声ファイルは共有しないでください。
