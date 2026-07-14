#!/bin/zsh
set -u

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

osascript <<APPLESCRIPT
tell application "Terminal"
  activate
  do script "cd ${ROOT_DIR:q} && ./run_jgrade_console.command"
end tell
APPLESCRIPT
