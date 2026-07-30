#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR" || exit 1

export PYTHONIOENCODING=utf-8

clear
echo "J-GRADE Speech Level Console"
echo "============================"
echo
echo "音声ファイルを選ぶと、ひらがなTranscript、流暢性指標、CEFR推定をこの画面に表示します。"
echo

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[エラー] .venv/bin/python が見つかりません。"
  echo
  echo "先に以下を実行してください:"
  echo "  uv sync --frozen"
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
