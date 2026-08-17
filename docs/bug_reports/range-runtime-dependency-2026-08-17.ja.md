# Range 実行時依存関係インシデント — 2026-08-17

## 概要

ターミナルコンソールは Fluency の後、Range 解析の前に `ModuleNotFoundError: No module named 'sudachipy'` で停止しました。

## 再現手順

1. `./open_jgrade_console_terminal.command` を起動する。
2. 音声を選択して Fluency 抽出を完了する。
3. Range 初期化時のエラーを確認する。

起動用環境だけで再現する最小コマンド:

```sh
.venv/bin/python -c "from jgrade_eval.range import RangeExtractor; RangeExtractor.default()"
```

## 証拠と時系列

| 時点 | 事象 |
|---|---|
| Range 実装時 | `SudachiPy` と `SudachiDict-core` を `pyproject.toml` に追加した。 |
| コンソール起動時 | ランチャーが `.venv/bin/python -m jgrade_eval` を実行した。 |
| 障害発生時 | `.venv` が `sudachipy` を import できなかった。 |
| 調査時 | システム Python では import でき、先行テストが別インタープリタで走っていたことを確認した。 |

## なぜなぜ分析

1. なぜ Range が失敗したか。`sudachipy` を import できなかったため。
2. なぜ import できなかったか。ランチャーの `.venv` に入っていなかったため。
3. なぜ `.venv` に入っていなかったか。依存追加後に同期していなかったため。
4. なぜ同期漏れになったか。ロックファイルを再生成していなかったため。
5. なぜテストで検出できなかったか。システム Python でテストし、`.venv/bin/python` を使わなかったため。

## 特性要因（フィッシュボーン）

- **依存関係:** `pyproject.toml`、ロックファイル、導入済み環境が乖離した。
- **プロセス:** 起動用インタープリタのスモークテストがなかった。
- **ツール:** `uv` が利用できず、前回の変更でロック更新を行わなかった。
- **コード:** SudachiPy は遅延 import のため、FakeTokenizer の単体テストでは実行されなかった。

## 修正と再発防止

- `pyproject.toml` から `uv.lock` を再生成し、`.venv` を同期する。
- デフォルト `RangeExtractor` の回帰テストを追加する。
- コンソールランチャーが音声処理の前に `RangeExtractor.default()` を初期化し、失敗時は `uv sync --frozen` を案内して終了するようにする。
- ターミナル起動前に `.venv/bin/python` で Range・コンソールテストを実行する。
- この記録とテストコマンドをリリースチェックリストに残す。
