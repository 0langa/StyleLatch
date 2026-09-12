# Providers

StyleLatch targets Codex and Claude Code from one set of files. This page
records what each host actually gives us, and where that was checked.

Dated evidence for every claim below lives in
[`.ai/official-docs-cache/`](../.ai/official-docs-cache/). When a claim here
and the cache disagree, the cache is older — re-check the source it names.

## Capability matrix

| | Claude Code | Codex |
|---|---|---|
| `SessionStart` hook | yes | yes |
| `SessionStart` matchers | `startup`, `resume`, `clear`, `compact`, `fork` | fires on session start |
| `UserPromptSubmit` hook | yes | yes |
| `Stop` hook | yes | yes |
| `hookSpecificOutput.additionalContext` | yes | yes, added as developer context |
| `hooks/hooks.json` auto-discovered at plugin root | yes | yes |
| Skills at `skills/<name>/SKILL.md` auto-discovered | yes | yes |
| Slash command at `commands/<name>.md` | yes | not used by StyleLatch |
| Plugin root env var | `CLAUDE_PLUGIN_ROOT` | `PLUGIN_ROOT`, plus `CLAUDE_PLUGIN_ROOT` as an alias |
| Writable data dir env var | `CLAUDE_PLUGIN_DATA` | `PLUGIN_DATA`, plus `CLAUDE_PLUGIN_DATA` as an alias |
| Project root env var | `CLAUDE_PROJECT_DIR` | not documented |
| Hooks need a one-time trust step | no | **yes** — Settings › Coding › Hooks |

The output JSON shape is identical on both, which is why one `hooks/hooks.json`
and one pair of scripts serve both hosts.

## Manifests

Three manifests describe the same plugin. A test keeps them in agreement.

| File | Read by | Why it exists |
|---|---|---|
| `plugin.json` | portable spec clients, Codex | The vendor-neutral [Agent Plugins 1.0.0](https://agent-plugins.org/) manifest. |
| `.claude-plugin/plugin.json` | Claude Code | Where Claude Code looks. |
| `.codex-plugin/plugin.json` | Codex | Legacy fallback overlay, kept for older Codex builds. |

`.claude-plugin/marketplace.json` is separate: it makes the repository
installable as its own one-plugin marketplace.

**None of them declares a `hooks` path.** `hooks/hooks.json` is auto-discovered
by both hosts, and declaring it as well double-registers on Claude Code and
fails the plugin load with *Duplicate hooks file*. There is a test for this.

## What each layer depends on

| Layer | Needs | If the host does not provide it |
|---|---|---|
| 1 | nothing — a line in the user's own instructions file | always works |
| 2 | `SessionStart` + `additionalContext` | no style at session start; layer 3 still re-states it every turn |
| 3 | `UserPromptSubmit` + a readable prompt field | no anti-drift nudge; layer 2 still delivers at session start |
| 4 | `Stop` + a readable `transcript_path` | no adherence measurement and no corrections; every other layer is unaffected |

The layers degrade independently, which is the point of having three.

## Payload fields

Claude Code sends the message as `prompt`. Codex's field name is not
documented, so `_style.prompt_from_payload` tries the plausible ones in order:
`prompt`, `user_prompt`, `userPrompt`, `text`, `message`, `input`.

If a host ever sends something else, `::test on` prints the payload keys it
actually received, which is how a new field name gets identified for real
rather than guessed at.

Scopes need two more fields, both optional:

| Field | Used for | Missing means |
|---|---|---|
| `cwd` | finding the project root | project scope is refused, with a message saying why |
| `session_id` | the session latch, and retiring debug mode | session scope is refused |
| `transcript_path` | reading the finished reply back, and `::test verify` | nothing is measured, and nothing is recorded — a clean turn would be a lie |

Refusing is deliberate. A latch stored under an empty key could never be read
back, and the user would be told "latched" and then watch nothing happen.

## Installing

### Claude Code

```bash
claude plugin marketplace add 0langa/StyleLatch
claude plugin install stylelatch@stylelatch
```

The installed copy is a **snapshot**, not a link. After editing the repository,
`claude plugin update stylelatch@stylelatch` and start a new session. `::test`
says which of the two you are running, because this is the failure everybody
hits once.

### Codex

Point Codex at the plugin, then trust the hooks once in
**Settings › Coding › Hooks**. Until that is done the hooks do not run at all,
and `::test verify` will report both markers ABSENT.

### Both

Paste the snippet from [`AGENTS_SNIPPET.md`](../AGENTS_SNIPPET.md) into your
global instructions file. Once. It names no profile, so switching styles never
touches it again.
