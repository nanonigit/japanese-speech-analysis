#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

export PYTHONIOENCODING=utf-8

clear
echo "J-GRADE Speech Level Console"
echo "============================"
echo
echo "音声ファイルを選ぶと、5軸評価の根拠となる客観データをこの画面に表示します。"
echo "  - Fluency客観データ: ひらがなTranscript、発話時間、ポーズ、モーラ、流暢性指標"
echo "  - Range客観データ: 単語分割、語彙TTR、未知語、JLPT語彙分布、同音異義語候補"
echo "AI JudgeによるCEFR推定は、その後に参考情報として表示します。"
echo

print_sync_instructions() {
  echo "先に以下を実行してください:"
  echo "  uv sync --frozen"
}

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[エラー] .venv/bin/python が見つかりません。"
  echo
  print_sync_instructions
  echo
  if [[ -t 0 ]]; then
    printf "Enterキーで閉じます..."
    read -r _
  fi
  exit 1
fi

if ! ".venv/bin/python" -c "import sudachipy, sudachidict_core" >/dev/null 2>&1; then
  echo "[エラー] Rangeモジュールに必要なSudachiPy辞書が .venv にありません。"
  echo "Range処理の前に依存関係を同期してください。"
  echo
  print_sync_instructions
  echo
  if [[ -t 0 ]]; then
    printf "Enterキーで閉じます..."
    read -r _
  fi
  exit 1
fi

JUDGE_CONFIG="${JGRADE_JUDGE_CONFIG:-config/judge_llms.json}"
ARGS=(interactive --judge-config "$JUDGE_CONFIG")

if [[ -n "${JGRADE_JUDGE_MODE:-}" ]]; then
  ARGS+=(--judge-mode "$JGRADE_JUDGE_MODE")
fi

if [[ -n "${JGRADE_JUDGE_PROVIDERS:-}" ]]; then
  ARGS+=(--judge-providers "$JGRADE_JUDGE_PROVIDERS")
fi

if [[ -n "${JGRADE_AUDIO_DIR:-}" ]]; then
  ARGS+=(--audio-dir "$JGRADE_AUDIO_DIR")
fi

if [[ -n "${JGRADE_PROFILE:-}" ]]; then
  ARGS+=(--profile "$JGRADE_PROFILE")
fi

echo "設定ファイル: ${JUDGE_CONFIG}"
echo "注: 初期設定はAPIキーなしで試せる mock です。実LLM判定は config/judge_llms.json の judge_mode を live にしてください。"
echo "    一時的に上書きする場合は JGRADE_JUDGE_MODE=live ./run_jgrade_console.command でも起動できます。"
echo

".venv/bin/python" -m jgrade_eval "${ARGS[@]}"
STATUS=$?

echo
if [[ "$STATUS" -eq 0 ]]; then
  echo "完了しました。"
else
  echo "エラー終了しました: status=${STATUS}"
fi

if [[ -t 0 ]]; then
  echo
  printf "Enterキーで閉じます..."
  read -r _
fi

exit "$STATUS"
