#!/usr/bin/env bash
# Install this repo's rules, and with --agents its agents and commands, into ~/.claude.
# --link points each file at this repo, so `git pull` updates the install; --copy (the default) copies.
# A file it replaces is moved to ~/.claude/.sdlc-backup/<time>/ first; nothing is deleted.
set -euo pipefail

usage() { echo "usage: scripts/install.sh [--link|--copy] [--agents]" >&2; exit 2; }

mode=copy
with_agents=0
for arg in "$@"; do
  case "$arg" in
    --link) mode=link ;;
    --copy) mode=copy ;;
    --agents) with_agents=1 ;;
    *) usage ;;
  esac
done

repo="$(cd "$(dirname "$0")/.." && pwd)"
dest="${CLAUDE_HOME:-$HOME/.claude}"
backup="$dest/.sdlc-backup/$(date +%Y%m%d-%H%M%S)"
moved=0
overrides="$dest/.sdlc-local-overrides" # one path per line, e.g. agents/product-manager.md: your own version, never replaced

is_local() { [ -f "$overrides" ] && grep -qxF "$1" "$overrides"; }

place() { # place <source file> <target dir>
  local src="$1" dir="$2"
  local target="$dir/$(basename "$src")"
  mkdir -p "$dir"
  if is_local "$(basename "$dir")/$(basename "$src")"; then echo "keep local $(basename "$dir")/$(basename "$src")"; return; fi
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$src" ]; then return; fi
  if [ "$mode" = copy ] && [ -f "$target" ] && [ ! -L "$target" ] && cmp -s "$src" "$target"; then return; fi
  if [ -e "$target" ] || [ -L "$target" ]; then
    mkdir -p "$backup/$(basename "$dir")"
    mv "$target" "$backup/$(basename "$dir")/"
    moved=1
  fi
  if [ "$mode" = link ]; then ln -s "$src" "$target"; else cp "$src" "$target"; fi
  echo "$mode $(basename "$dir")/$(basename "$src")"
}

for f in "$repo"/rules/*.md; do place "$f" "$dest/rules"; done
if [ "$with_agents" = 1 ]; then
  for f in "$repo"/plugins/sdlc/agents/*.md; do place "$f" "$dest/agents"; done
  for f in "$repo"/plugins/sdlc/commands/*.md; do place "$f" "$dest/commands"; done
fi

if [ "$moved" = 1 ]; then echo "replaced files were moved to $backup"; fi
version="$(sed -n 's/.*"version": "\(.*\)".*/\1/p' "$repo/plugins/sdlc/.claude-plugin/plugin.json")"
echo "sdlc $version installed from $repo ($mode)"
