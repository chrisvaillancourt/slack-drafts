#!/bin/sh
# Install slack-drafts for any agent harness. Parts:
#   cli     bin/slack-drafts on your PATH. Every harness runs it from its shell tool.
#   skill   skills/slack-drafts linked into ~/.agents/skills (read by omp, Codex,
#           Amp and others) and ~/.claude/skills (Claude Code), so edits reach
#           new sessions with no reinstall.
# With no arguments it installs both. Then log in once: slack-drafts auth login
set -eu
repo=$(cd "$(dirname "$0")" && pwd)
bin="${SLACK_DRAFTS_BIN_DIR:-$HOME/.local/bin}"

link() { # link SRC DEST
  if [ -e "$2" ] && [ "$(readlink "$2")" != "$1" ]; then
    echo "install.sh: $2 exists and isn't ours; move it aside first" >&2
    exit 1
  fi
  mkdir -p "$(dirname "$2")"
  ln -sfn "$1" "$2"
  echo "linked $2 -> $1"
}

install_cli() {
  link "$repo/bin/slack-drafts" "$bin/slack-drafts"
  case ":$PATH:" in *":$bin:"*) ;; *) echo "note: $bin is not on PATH" >&2 ;; esac
  command -v uv >/dev/null 2>&1 || echo "note: slack-drafts runs with uv, which is not on PATH" >&2
  command -v agent-browser >/dev/null 2>&1 || echo "note: \`slack-drafts auth login\` needs agent-browser" >&2
}

install_skill() {
  link "$repo/skills/slack-drafts" "$HOME/.agents/skills/slack-drafts"
  if [ -d "${CLAUDE_CONFIG_DIR:-$HOME/.claude}" ]; then
    link "$HOME/.agents/skills/slack-drafts" "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/slack-drafts"
  fi
}

[ $# -gt 0 ] || set -- cli skill
for part in "$@"; do
  case "$part" in
    cli) install_cli ;;
    skill) install_skill ;;
    *) echo "usage: install.sh [cli] [skill]" >&2; exit 2 ;;
  esac
done
