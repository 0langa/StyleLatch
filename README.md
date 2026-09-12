# StyleLatch

StyleLatch provides switchable output styles for **Codex** and **Claude Code**, from one shared
set of files. Codex is the target; Claude Code comes free because both use the
same hook shape.

Status: v0.1.0, local only. Nothing is installed into any provider yet.

## The idea

Two ideas do the work.

**1. Compose at switch time, not at read time.**
You pick `profile + modifiers`. A script merges them into one flat file with
the real rules already written out. The agent reads one file and never has to
resolve an id to a path. No hops to drop.

**2. Three layers, because one is not enough.**
An output style is a *continuous* constraint — it governs every sentence, and
nothing re-triggers it. So it decays. Layering is the fix:

| Layer | Where | Fires | Cost when no style is set |
|---|---|---|---|
| 1 | `AGENTS.md` / `CLAUDE.md` line | always in context | zero |
| 2 | `SessionStart` hook | startup, resume, clear, compact, **fork** | zero |
| 3 | `UserPromptSubmit` hook | every turn | zero |

Layer 3 injects a ~30-word reminder, never the whole contract. That is what
makes a per-turn hook affordable.

When no style is set every hook prints `{"continue": true}` and stops. It
costs nothing, and no agent goes hunting for a directory.

## Layout

```
styles/PROFILES/      01-eli5.md, 02-terse.md, 03-deep-technical.md
styles/MODIFIERS/     01-full-paths.md, 02-no-preamble.md, 03-show-evidence.md
scripts/style.py      the switcher
hooks/hooks.json      layer 2 + layer 3 registration
hooks/scripts/        _style.py, session_start.py, user_prompt_submit.py
AGENTS_SNIPPET.md     the one line for layer 1
tests/                15 tests, stdlib unittest, no pytest needed
.ai/official-docs-cache/   dated evidence for every provider claim made here
```

## Use it

```bash
py -3 scripts/style.py list
py -3 scripts/style.py set eli5 --with no-preamble
py -3 scripts/style.py show
py -3 scripts/style.py off
```

Ids work too, and stack: `py -3 scripts/style.py set 01 --with 02 --with 03`.

Then start a new session or fork the current one.

## Where state lives

**Outside the plugin**, so a plugin update never wipes your active style:

1. `$STYLELATCH_HOME` — explicit override, always wins
2. `$PLUGIN_DATA/stylelatch` — Codex hands plugins a writable data dir
3. `~/.stylelatch` — default

Holds `ACTIVE.md` (the composed rules) and `state.json` (what is on, plus the
per-turn nudge). Writes are atomic, so a hook never reads half a file.

## Add a style

Drop a file in `styles/PROFILES/` or `styles/MODIFIERS/`:

```markdown
---
id: "04"
name: your-name
nudge: The 30-word version, injected every turn. Keep it sharp.
---

The full rules. This text lands verbatim in ACTIVE.md.
```

`nudge` is required on profiles and the test suite enforces it.

## Install (not done yet — read first)

Nothing here touches `~/.codex/` or your Codex app. When you are ready:

1. Paste the snippet from `AGENTS_SNIPPET.md` into your global instructions.
2. Point your provider at this directory as a plugin.
3. **Codex only:** trust the hooks once in **Settings > Coding > Hooks**.

## Tests

```bash
py -3 -m unittest discover -s tests -v
```

They run against a temp dir, never your real `~/.stylelatch`.

## Known gaps for v0.2

- No slash command yet. The CLI is the only switcher.
- Profile bodies are seeds, not tuned.
- Untested inside a real Codex session. Layer 3 is confirmed by docs, not yet
  by your own eyes.
