#!/usr/bin/env bash
# Report how ~/.claude compares with this repo (linked, same copy, drifted, missing),
# whether settings.json wires the gate hooks, and that plugin.json and marketplace.json
# carry the same version, and, when a lessons library exists, that each promoted lesson's text is
# in the installed agents it names (check_lessons.py). A missing rule is a problem, since the
# plugin does not ship rules. Exits non-zero on drift, a missing rule, a version mismatch or a
# promoted lesson missing from an installed agent, or, when SDLC_EVALS names an eval folder, a
# frozen eval case that changed or is missing. Reads only; writes nothing.
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
dest="${CLAUDE_HOME:-$HOME/.claude}"
drift=0
overrides="$dest/.sdlc-local-overrides" # files you keep your own version of, listed by install.sh's rules

check() { # check <source file> <installed dir> [required]
  local src="$1" target="$2/$(basename "$1")" state
  if [ -f "$overrides" ] && grep -qxF "$(basename "$2")/$(basename "$1")" "$overrides"; then state=local
  elif [ -L "$target" ] && [ "$(readlink "$target")" = "$src" ]; then state=linked
  elif [ ! -e "$target" ] && [ "${3:-}" = required ]; then state=MISSING; drift=$((drift + 1))
  elif [ ! -e "$target" ]; then state=missing
  elif cmp -s "$src" "$target"; then state=same
  else state=DRIFT; drift=$((drift + 1)); fi
  printf '%-8s %s\n' "$state" "${target#"$dest"/}"
}

for f in "$repo"/rules/*.md; do check "$f" "$dest/rules" required; done
for f in "$repo"/plugins/sdlc/agents/*.md; do check "$f" "$dest/agents"; done
for f in "$repo"/plugins/sdlc/commands/*.md; do check "$f" "$dest/commands"; done

gate="$repo/plugins/sdlc/hooks/sdlc_gate.py"
wired=0 # both events are needed: the prompt hook sets the lock that the tool hook enforces
for mode in prompt tool; do
  if grep -qF -e "$gate $mode" -e "$gate\\\" $mode" "$dest/settings.json" 2>/dev/null; then wired=$((wired + 1)); fi
done
case "$wired" in
  2) hooks=linked ;;
  0) hooks=missing ;;
  *) hooks=PARTIAL; drift=$((drift + 1)) ;;
esac
printf '%-8s %s\n' "$hooks" "settings.json hooks (prompt and tool) -> plugins/sdlc/hooks/sdlc_gate.py"
# the mcp mode keeps Atlassian writes out of a Jira run; not counted as drift, since a plugin install has it in hooks.json
if grep -qF -e "$gate mcp" -e "$gate\\\" mcp" "$dest/settings.json" 2>/dev/null; then mcp=linked; else mcp=missing; fi
printf '%-8s %s\n' "$mcp" "settings.json mcp gate (no MCP write in a Jira run) -> plugins/sdlc/hooks/sdlc_gate.py mcp"
if grep -qF -e "$gate jira-seen" -e "$gate\\\" jira-seen" "$dest/settings.json" 2>/dev/null; then seen=linked; else seen=missing; fi
printf '%-8s %s\n' "$seen" "settings.json jira-seen (a Jira run cannot be approved without it) -> plugins/sdlc/hooks/sdlc_gate.py jira-seen"

version_of() { sed -n 's/.*"version": "\(.*\)".*/\1/p' "$1" | head -1; }
plugin_version="$(version_of "$repo/plugins/sdlc/.claude-plugin/plugin.json")"
market_version="$(version_of "$repo/.claude-plugin/marketplace.json")"
if [ "$plugin_version" != "$market_version" ]; then
  echo "version mismatch: plugin.json $plugin_version, marketplace.json $market_version"
  drift=$((drift + 1))
fi

lessons="$dest/lessons/LESSONS.md"
if [ -f "$lessons" ]; then
  python3 -I "$repo/scripts/check_lessons.py" --lessons "$lessons" --agents "$dest/agents" || drift=$((drift + 1))
fi

evals="${SDLC_EVALS:-}" # the eval folder that holds suites/regression.json; verify.sh names plugins/sdlc/evals
if [ -n "$evals" ] && [ -f "$evals/suites/regression.json" ] && [ -d "$evals/baselines" ]; then
  python3 -I "$repo/scripts/suite.py" check "$evals/suites/regression.json" "$evals" \
    --baselines "$evals/baselines" --agents-dir "$evals/../agents" || drift=$((drift + 1))
elif [ -n "$evals" ] && [ -f "$evals/suites/regression.json" ]; then
  python3 -I "$repo/scripts/suite.py" check "$evals/suites/regression.json" "$evals" || drift=$((drift + 1))
  skipped=" Agent-vs-baseline comparison NOT run: no baselines in $evals, only the frozen cases were checked."
fi

echo "sdlc $plugin_version: $drift problem(s).${skipped:-} 'missing' agents, commands and hooks are normal when the plugin is installed instead; a MISSING rule is not."
[ "$drift" = 0 ]
