# J-GRADE STT 検証環境

外国人日本語学習者の発話を **ひらがなのみ・意味補正なし** でテキスト化するSTTモデルの検証環境。

## 使用モデル

| ラベル | モデルID | ライセンス |
|--------|---------|---------|
| モデルA（推奨） | sakasegawa/japanese-wav2vec2-large-hiragana-ctc | Apache-2.0 |
| モデルB | slplab/wav2vec2-xls-r-300m-japanese-hiragana | 記載なし |
| モデルC | vumichien/wav2vec2-large-xlsr-japanese-hiragana | Apache-2.0 |

---

## 環境構築手順

### 前提

- macOS（Apple Silicon 推奨）
- Git
- [uv](https://docs.astral.sh/uv/)
- インターネット接続（モデルの初回ダウンロードに必要）

### 1. リポジトリのクローン

```bash
git clone --recurse-submodules https://github.com/goyojima-hash/japanese-speech-analysis.git
cd japanese-speech-analysis
```

すでにクローン済みの場合は、submoduleを初期化してください。

```bash
git submodule update --init --recursive
```

### 2. Python環境の構築

```bash
uv python install 3.11
uv sync --frozen
```

`.python-version`と`uv.lock`に基づいて、プロジェクト内の`.venv/`へ環境が作成されます。

### 3. モデルA チェックポイントのダウンロード（約600MB）

```bash
uv run python - <<'PY'
from huggingface_hub import hf_hub_download

hf_hub_download(
    repo_id="sakasegawa/japanese-wav2vec2-large-hiragana-ctc",
    filename="best-medium-ep5-inference.pt",
    local_dir="hiragana-asr/models/checkpoints",
)
print("ダウンロード完了")
PY
```

### 4. 3モデルの読み込み確認

```bash
uv run python check_models.py
```

---

## フォルダ構成

```
japanese-speech-analysis/
├── audio/                          # 音声ファイル（MP3/WAV等）
│   ├── burmese_japanese_1min.mp3
│   ├── indonesian_japanese_1min.mp3
│   └── vietnamese_japanese_1min.mp3
├── hiragana-asr/                   # モデルA用submodule
│   ├── models/checkpoints/
│   │   └── best-medium-ep5-inference.pt  # チェックポイント（要ダウンロード）
│   └── src/asr/                    # モデルAの推論コード
├── .venv/                          # uvが作成するPython仮想環境
├── pyproject.toml                  # 直接依存関係
├── uv.lock                         # 解決済み依存関係
├── check_models.py                 # フェーズ1: モデル読み込み確認
├── phase2_single_test.py           # フェーズ2: 単体動作確認
├── phase3_batch.py                 # フェーズ3: 一括処理
├── jgrade_eval/                    # J-GRADEタスク達成度評価エンジン
├── examples/                       # 評価エンジンの検証用JSON
├── tests/                          # ローカル検証テスト
├── results.csv                     # フェーズ3の出力結果
└── report.md                       # 検証レポート
```

---

## 実行手順

### フェーズ1: モデル読み込み確認

```bash
uv run python check_models.py
```

3モデルすべて「✓ 読み込み成功」と表示されれば OK。

### フェーズ2: 単体動作確認（1ファイル）

```bash
uv run python phase2_single_test.py
```

デフォルトは `audio/vietnamese_japanese_1min.mp3` を対象に3モデルで実行。  
対象ファイルを変更する場合はスクリプト内の `AUDIO_FILE` を編集。

### フェーズ3: 一括処理（全ファイル）

```bash
uv run python phase3_batch.py
```

`audio/` フォルダ内の全音声ファイルを3モデルで処理し、`results.csv` に保存。

### J-GRADE評価エンジン: ローカル検証

STT/流暢さ分析の後段として、Raw Transcriptと流暢さ指標を受け取り、3つのLLM Judgeの評価結果を多数決で集約する評価エンジンを追加しています。
実LLM APIキーがなくても、fixture JSONでプロンプト生成・多数決・CEFR合否判定・人間教師ラベルとのズレ測定を検証できます。

#### テスト用コンソール入口

GitHubから試す人は、環境構築後に `run_jgrade_console.command` を起動してください。macOSではFinderでダブルクリックするとTerminalが開き、音声ファイル選択から結果表示まで同じコンソール画面で進みます。

Judge LLMの選択は `config/judge_llms.json` で管理します。協力者はコードを編集せず、この設定ファイルの `judge_mode` と `live_judges` だけを変更してください。APIキーは `.env.example` を `.env` にコピーして、使うプロバイダのキーだけを入れます。

```bash
# Terminalから起動する場合
./run_jgrade_console.command

# 実LLM Judgeで試す場合（一時上書き。通常は config/judge_llms.json を編集）
JGRADE_JUDGE_MODE=live ./run_jgrade_console.command

# 実LLM Judgeのモデルを固定する場合
JGRADE_JUDGE_MODE=live \
JGRADE_JUDGE_PROVIDERS=anthropic:claude-sonnet-4-6,openai:gpt-5.4-mini,gemini:gemini-3.1-pro-preview \
./run_jgrade_console.command
```

起動直後に `=== Judge設定 ===` が表示されます。ここで `mock Judgeで試す`、`設定ファイルのJudge 1〜3を使う`、`Judge 1〜3をこの画面で選ぶ` から選択できます。実LLM Judge候補には `key=set`、`key=missing`、`key=invalid` のようにAPIキー状態が表示されます。APIキーの値そのものは表示しません。

Judge設定の後に、ファイル選択ダイアログ、パス入力、または `audio/` 内のサンプル音声から音声を選べます。出口はコンソール末尾の `=== 最終結果 ===` です。ここに `CEFRレベル`、`タスク達成度`、`信頼度`、`人間確認`、判定理由、ひらがなTranscript量、流暢性指標、Judgeごとの推定レベルが表示されます。

最終結果の後に `=== ユーザーレベル確認 ===` が表示されます。協力者はこのファイルの正しいCEFRレベルを選ぶか、`スキップ` できます。ユーザー選択レベルがSystemJudgeの判定と異なる場合は、`tuning_profiles/base.json` などのチューニングプロファイルに `level_overrides` と `tuning_examples` を自動保存し、修正内容をコンソールに表示します。同じ音声は次回以降、保存された補正を判定過程で使います。

協力者に送る詳しい手順と報告テンプレートは `docs/collaborator_testing.md` にあります。

```bash
# Judge A（Claude想定）に渡すプロンプトを生成
uv run python -m jgrade_eval prompt \
  --input examples/jgrade_roleplay_input.json \
  --judge A \
  --model-family claude

# 3 Judge x 3ロールプレイの多数決とCEFR合否判定
uv run python -m jgrade_eval consensus \
  --input examples/jgrade_judge_results.json \
  --output outputs/jgrade_decision.json

# 人間教師ラベルとAI判定のズレを集計
uv run python -m jgrade_eval benchmark \
  --input examples/jgrade_benchmark.json \
  --output outputs/jgrade_benchmark_report.json

# 音声を取り込み、客観データだけを確認
uv run python -m jgrade_eval extract-objective \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --output outputs/jgrade_objective_data.json

# 客観データ抽出からJFS判定ロジックまで疎通確認
uv run python -m jgrade_eval evaluate-audio \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --judge-mode mock \
  --output outputs/jgrade_audio_report.json

# 実LLM Judgeを1〜3つ選んで評価（APIキーは.envまたは環境変数から読む）
uv run python -m jgrade_eval evaluate-audio \
  --manifest examples/jgrade_audio_manifest.json \
  --base-dir . \
  --judge-mode live \
  --judge-providers anthropic:claude-sonnet-4-6,openai:gpt-5.4-mini,gemini:gemini-3.1-pro-preview \
  --output outputs/jgrade_live_report.json

# 対話式: 音声を選ぶ -> 客観データ表示 -> 1〜3 Judge CEFR推定 -> CEFR多数決表示
# 音声はファイル選択ダイアログ、パス入力、またはサンプル音声から選べます
uv run python -m jgrade_eval interactive --judge-mode mock

# 対話式で実LLMを使う前に、ローカル.envへキーを設定
uv run python -m jgrade_eval configure-keys

# 対話式: Judge 1/2/3のLLMを番号で選ぶ -> 音声を選ぶ -> CEFR自動推定
uv run python -m jgrade_eval interactive --judge-mode live

# 実LLMをCLI引数で固定して評価
uv run python -m jgrade_eval interactive \
  --judge-mode live \
  --judge-providers anthropic:claude-sonnet-4-6,openai:gpt-5.4-mini,gemini:gemini-3.1-pro-preview

# 公式JFスタンダード・ロールプレイ音声をローカルに取得
# 音声は audio/ に集約し、公式JF音声だけgitには入れません
# 評価PDFと取得manifestは data/external/ に保存します
uv run python -m jgrade_eval download-jfs-samples \
  --output data/external/jfs_roleplay/download_manifest.json

# 取得した公式音声をチューニング/ベンチマーク用データセットへ変換
uv run python -m jgrade_eval prepare-jfs-dataset \
  --output data/tuning/jfs_roleplay_dataset.json

# 公式データセットでCEFR推定を検証
uv run python -m jgrade_eval.tuning_runner \
  --dataset data/tuning/jfs_roleplay_dataset.json \
  --profile tuning_profiles/base.json \
  --out outputs/jfs_roleplay_tuning_report.json

# HTTP APIを起動（mock JudgeならAPIキーなしで動作）
.venv/bin/python -m uvicorn jgrade_eval.api:app --host 127.0.0.1 --port 8000

# 別ターミナルから音声をアップロードして判定
curl -s -X POST http://127.0.0.1:8000/api/v1/speech-level-evaluations \
  -F "audio=@audio/vietnamese_japanese_1min.mp3" \
  -F "external_id=local-api-smoke" \
  -F "language=ja" \
  -F "judge_mode=mock" \
  -F "roleplay_task=社会的な話題について、自分の考えと理由を述べる。" \
  | python -m json.tool

# テスト
uv run python -m unittest discover -s tests
```

対話式CLIではCEFRレベルやロールプレイ課題を人間が入力せず、客観データをもとに1〜3つのLLM Judgeが `A1`〜`C2` を推定し、多数決で最終CEFR推定を表示します。標準構成は3 Judgeですが、ローカル検証ではJudge 2/3をスキップできます。プロバイダは重複できません。
対話式CLIでは一部のJudge APIが失敗しても、少なくとも1つのJudgeが成功していれば、その成功分だけでCEFR集約を続行し、失敗したJudgeは警告として表示します。

HTTP APIは `POST /api/v1/speech-level-evaluations` で音声ファイルまたは `audio_url` を受け取り、`final_cefr_level`、`summary`、`reasons`、`objective_data`、`judge_results`、`needs_human_review` を返します。現在のローカルAPIは1リクエスト内で処理を完了して返すMVPです。将来の外部System統合では、同じレスポンス形を保ったまま非同期ジョブ化する想定です。

自分で用意した複数音声をmanifestで試す場合は、`examples/jgrade_audio_manifest.json` と同じ形式で、候補者・試験レベル・ロールプレイごとの `audio_path`、タスク、JFS can-do基準、期待される情報を指定できます。`extract-objective` はこのリポジトリの `fluency.py` を使い、ひらがな文字起こし、発話率、ポーズ、モーラ速度、発話区間を出力します。`judge-mode mock` はAPIキーなしの疎通確認用で、正式なJFS判定ではありません。

テスト用音声は `audio/` に集約して管理します。公式JFスタンダードのロールプレイ音声は、`examples/jfs_roleplay_catalog.json` に出典URL・レベル・達成度・評価PDFをまとめています。対象はA2/B1/B2/C1の13サンプルです。JFロールプレイテストにはC2ロールプレイがないため、C2判定はこの公式音声だけでは検証できません。サイトポリシー上、公式音声/PDF本体はローカル利用にとどめ、公式音声は `.gitignore` で追跡しないでください。

実LLMで評価する場合は `configure-keys` を使うか、`.env.example` を `.env` にコピーして、使うプロバイダのキーだけを入れてください。`configure-keys` は各入力後と最後に `set/missing` だけを表示し、キー値は表示しません。対応するテキストJudgeプロバイダは `anthropic`, `openai`, `gemini`, `xai`, `groq` です。`interactive --judge-mode live` で `--judge-providers` を省略すると、Judge 1/2/3のLLMを番号で選べます。Judge 1で選んだプロバイダは2/3候補から消え、Judge 2/3ではスキップできます。`elevenlabs` はキーの保存状態だけ表示しますが、現時点ではテキストJudgeとしては使わず、将来の音声機能用に予約しています。

`uv` がPATHにないローカル環境では、既存の仮想環境があれば `.venv/bin/python -m jgrade_eval ...` または `.venv/bin/python -m unittest discover -s tests` で同じ検証を実行できます。

詳しい設計とAWS/API化の接続方針は `docs/jgrade_eval.md` を参照してください。

### J-GRADEチューニング画面

CLIや一括評価で判定した音声は、レビュー用データセット `data/tuning/review_samples.json` に蓄積できます。教師は画面上でCEFRだけを修正し、その修正から `level_overrides`、補正統計、Few-shot例がプロファイルへ保存されます。

```bash
# 教師ラベルCSVからチューニング用manifestを作成
.venv/bin/python tools/prepare_tuning_dataset.py \
  --labels examples/tuning_labels.csv \
  --audio-dir . \
  --out data/tuning/example_manifest.json

# 画面なしで一括評価を実行
.venv/bin/python -m jgrade_eval.tuning_runner \
  --dataset data/tuning/example_manifest.json \
  --profile tuning_profiles/base.json \
  --base-dir . \
  --out outputs/tuning_runs/example_mock.json

# チューニング画面を起動（判定履歴の蓄積ストアを開く）
.venv/bin/streamlit run tools/tuning_app.py -- \
  --dataset data/tuning/review_samples.json \
  --profile tuning_profiles/base.json \
  --output outputs/tuning_runs/example_mock.json \
  --base-dir .
```

`interactive` CLIで判定した音声は、標準では `data/tuning/review_samples.json` に自動保存されます。別の保存先にしたい場合は `--review-store` を指定してください。

`tools/tuning_app.py` には `Review Samples`, `CEFR Tuning`, `Metrics`, `Export` の4タブがあります。チューニングとして変更できる入力は `Corrected CEFR` だけです。プロンプト本文や任意メモは画面から直接編集せず、CEFR修正履歴をもとに内部で自動更新します。`Run benchmark` を押すと、レビュー用データセットの客観データと保存中のプロファイル設定でJudge評価を一括実行し、結果を同じレビュー用データセットへ戻します。

`CEFR Tuning` で教師が正しいCEFRへ修正し、`Apply CEFR correction` を押すと、そのサンプルIDに対する `level_overrides`、AI推定から教師修正への `level_correction_stats`、次回以降のLLMプロンプトに入る `tuning_examples` がプロファイルへ保存されます。これにより、同じサンプルは次回から修正CEFRが適用され、類似例はFew-shotと補正傾向としてJudgeに渡されます。

補正適用・rollbackのたびに `changed_at` と `summary` 付きの履歴を残します。履歴は直近10件まで保持し、`Export` タブの `Recent profile changes` から任意の履歴へ戻せます。

教師ラベルCSVは以下の列を想定します。

```csv
sample_id,audio_path,human_cefr,human_rating,notes
a2_001,/Users/naoki/Desktop/A2_001.mp3,A2,○,
b1_001,/Users/naoki/Desktop/B1_001.mp3,B1,○,
```

#### 音声ファイルの命名規則

ファイル名に話者属性を含めること（自動判定される）：

| 含める文字列 | 判定される話者属性 |
|------------|----------------|
| `burmese` または `myanmar` | burmese |
| `indonesian` または `indonesia` | indonesian |
| `vietnamese` または `vietnam` | vietnamese |

---

## 音声ファイルの前処理

スクリプトは音声ファイルを自動で以下の形式に変換して処理します：

- サンプリングレート: **16kHz**（モデルの要求仕様）
- チャンネル: **モノラル**
- 対応形式: MP3, WAV, M4A, FLAC, OGG

変換は `librosa` が担当するため、別途変換ツールは不要。

---

## 出力 CSV の列説明

| 列名 | 内容 |
|------|------|
| ファイル名 | 処理した音声ファイル名 |
| 話者属性 | ファイル名から自動判定（burmese / indonesian / vietnamese） |
| モデル名 | HuggingFace モデルID |
| モデルラベル | モデルA / B / C |
| 出力テキスト | 文字起こし結果 |
| 漢字混入フラグ | True / False |
| カタカナ混入フラグ | True / False（「ー」長音符は除外） |
| 処理時間_秒 | 推論にかかった秒数 |
| 音声長_秒 | 音声ファイルの長さ（秒） |

---

## トラブルシューティング

### `torchaudio.load` でエラーが出る

torchaudio 2.11以降はFFmpegが必要です。このプロジェクトでは `librosa` で代替しているため問題ありません。

### モデルAのロードで `UNEXPECTED` キーの警告が出る

```
project_hid.bias | UNEXPECTED
```

推論には影響しません。無視して問題ありません。

### メモリ不足・速度低下

3モデル同時ロードでApple Silicon GPUのメモリ競合が発生する場合があります。  
1モデルずつ実行することで処理速度が大幅に改善します（フェーズ2参照）。

---

## 検証結果サマリー

→ 詳細は [report.md](report.md) を参照

| モデル | 漢字混入 | カタカナ混入 | 処理速度（60秒/単独） | 推奨度 |
|--------|---------|------------|-------------------|------|
| **A (sakasegawa)** | 0% | 0% | **約10秒** | **★★★ 推奨** |
| B (slplab) | 0% | 0% | 約34秒 | ★★ 参考 |
| C (vumichien) | 0% | 0% | 約302秒 | ★ 実用困難 |
