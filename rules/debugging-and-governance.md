# Debugging & governance

## Evidence before fixes
> Learned from a bug that stayed live for days: the evidence sat in a log nobody opened, the first fix was a theory, and every test stubbed the host. Each rule has a check.

- **Read the host's own logs before proposing a cause.** For a bug in how a host app (the Claude desktop app, CLI, an IDE) draws or runs a plugin or mod, run `grep -c '<plugin name>' ~/Library/Logs/Claude/*.log` and look in `~/.claude/debug/*.txt`, then quote each command with its count ("0 hits in <file>" counts). Known place: the Claude desktop app logs faults of plugin surfaces in `claude.ai-web.log`, not `main.log`. Check: the first message of the diagnosis has a `Logs searched:` line.
- **A fix names its evidence:** a log line quoted with file and line, or the name of a check that fails before the change, in the commit body or the PR. With neither, the change may add the probe or log line, not the fix. Check: `git log -1 --format=%B` of a `fix:` commit holds an `Evidence:` line.
- **Label every root-cause claim `[measured]` or `[read]`.** "Plausible" and anything taken from reading code is `[read]`. A read-only check that takes minutes (a grep, a count) is run before the claim is ranked, never only listed.
- **One live thing per item is loaded before it merges.** A change that adds `setInterval`, another per-item timer, or a client, stream or subscription per item of a list needs a "Host load" line in the PR: 10 or more items, 60 seconds in the real host, its log read afterwards, the number of warnings. A test that stubs the host proves layout, not the host.
- **Know what the host loads before syncing a cache.** `ls -l` and the debug log say whether a plugin runs from its folder or from an installed copy; sync only what runs.
- **Reproduce before diagnosing,** and date every symptom in the logs: one that appears before the suspected cause shipped has a second cause, listed as open.

## Maintaining these rules
> Code quality contract. Every rule here is either enforced by a tool or checkable by grep. A rule that can't be checked is a wish — don't add it.

- A rule earns its place only if a violation is **detectable** — by ESLint, by CI, or by a grep you can write in one line. Prose that can't be checked gets deleted.
- Mechanical rules belong in tooling, not here. When a rule moves into ESLint, cut it down to one line pointing at the tool.
- Nested `CLAUDE.md` files describe **invariants and patterns** — never directory trees, file listings, or route tables. Those rot within a week and a stale map is worse than none.
- A failure that happens twice becomes a check, a lint rule, a hook or an edit to these files.
