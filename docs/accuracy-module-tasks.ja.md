# 正確さモジュール 実装計画

1. `AsrUnitEvidence`、`AsrAlignmentEvidence`、`AccuracyFactPacket` の失敗テストを先に書く。score／正誤／CEFRフィールドは拒否する。
2. Evidence v2を追加的に導入し、現在のWav2Vec2 CTC logitから単位別要約を作る。生logitは保存しない。
3. `accuracy.py` に独立した `collect(bundle, reference=None)` を実装し、共有Sudachiトークンを使う。
4. 明示的参照文だけに編集差分を許可し、未対応能力を理由付きで返す。
5. `ModuleRunner` と選択モジュール設定を追加し、API/CLIの既存互換性を維持する。
6. モジュール独立性、キャッシュ来歴、API/CLI、教師レビュー済みfixtureを検証してからJudge入力に有効化する。
