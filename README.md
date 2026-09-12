# StyleLatch

Switchable output styles for **Codex** and **Claude Code**, from one shared set
of files, switched by typing into the chat.

```
::terse

::eli5+no-preamble  explain what this regex does

::off
```

That is the entire interface. There is no command to run and no session to
restart: the switch happens inside a hook that was going to fire anyway.

Status: v0.1.0 on the marketplace, `main` is working toward v0.2.0.

---

## Why this exists

An output style is a **continuous** constraint. It governs every sentence, and
nothing in the conversation re-triggers it. So it decays — usually somewhere
around the fifth reply, and reliably after a compact.

Two ideas fix that.

### 1. Compose at switch time, not at read time

You pick `profile + modifiers`. They are merged **then**, into one flat file
with the real rules already written out. The agent reads one file and never
resolves an id to a path. No hops to drop.

### 2. Three layers, because one is not enough

| Layer | Where | Fires | Cost when no style is set |
|---|---|---|---|
| 1 | `AGENTS.md` / `CLAUDE.md` line | always in context | zero |
| 2 | `SessionStart` hook | startup, resume, clear, compact, **fork** | zero |
| 3 | `UserPromptSubmit` hook | every turn | zero |

Layer 3 injects a ~30-word reminder, never the whole contract. That budget is
the only reason a per-turn hook is affordable at all.

When no style is set every hook prints `{"continue": true}` and stops. It costs
nothing, and no agent goes hunting for a directory.

---

## Using it

Type a directive as the first thing in a message.

| You type | What happens |
|---|---|
| `::terse` | Latch the `terse` profile |
| `::eli5+no-preamble` | Latch a profile with modifiers stacked on |
| `::01+02` | Ids work too |
| `::terse fix the parser` | Latch it **and** do the task, in one message |
| `::?` | List every profile and modifier, and what is latched now |
| `::off` | Back to default behaviour |
| `::test` | Check StyleLatch itself |

The grammar is forgiving on purpose. `::terse`, `:: terse` and `: :terse` all
work, case is ignored, and a near miss gets a suggestion rather than silence:

```
::elif
StyleLatch: no style called 'elif'. Nothing changed. Did you mean ::eli5 ?
```

### Why `::`

`/` is slash-command territory in both apps and `#` is Claude Code's
add-to-memory shortcut. The host would eat either before a hook ever saw it.
`::` is claimed by nobody and almost never opens a sentence.

---

## When it does not seem to be working

Everything diagnostic lives behind one directive.

```
::test          run every structural check and report
::test on       debug mode: what each hook actually received, every turn
::test off      end debug mode now
::test canary   plant two high-entropy tokens and prove delivery
::test verify   search the host's own transcript for the injection
```

`::test` answers most questions on its own:

```
StyleLatch self-test

  PASS  state directory is writable
        C:\Users\you\.stylelatch
  PASS  style files parse
        4 profiles, 4 modifiers
  PASS  every style composes
  PASS  hook scripts and registration
        registered: SessionStart, UserPromptSubmit
  PASS  injection budget
        layer 2    863 chars  ~216 tokens  (cap 6000)
        layer 3    117 chars   ~29 tokens  (cap 300)

  plugin root   C:\Users\you\.claude\plugins\cache\...\0.1.0
                installed snapshot -- edits to the repo need a plugin update
  latched       02
```

That last line is there because it is the failure everybody hits once: the code
is right, the tests pass, and nothing changes, because the provider is running
a copy it made at install time.

**Debug mode ends by itself** — after 20 turns, after 60 minutes, or when the
session changes, whichever comes first. A diagnostic that outlives its
usefulness is exactly the clutter it was added to prevent.

### Proving it, rather than believing it

A model's account of its own context is not evidence; it confabulates in both
directions. A green hook indicator is not evidence either; it only proves a
script ran.

`::test canary` plants two high-entropy tokens, one per layer, then asks you to
start a fresh session and ask *what is your canary?* Both tokens back means
both layers deliver. One token means exactly one layer is broken, and tells you
which. That is proof.

`::test verify` reads the host's own transcript from disk — the file the host
writes with the exact payload it sent to the API. If the text is in there, it
reached the model, and there is nothing left to argue about.

---

## Layout

```
styles/PROFILES/       01-eli5.md, 02-terse.md, 03-deep-technical.md, 04-silent-run.md
styles/MODIFIERS/      01-full-paths.md, 02-no-preamble.md, 03-show-evidence.md, 04-red-balls.md
hooks/hooks.json       layer 2 + layer 3 registration
hooks/scripts/         _style.py, _directives.py, _diagnostics.py, and the two entrypoints
AGENTS_SNIPPET.md      the one line for layer 1
tests/                 stdlib unittest, no pytest needed
.ai/official-docs-cache/   dated evidence for every provider claim made here
```

---

## Where state lives

**Outside the plugin**, so an update never wipes your active style:

1. `$STYLELATCH_HOME` — explicit override, always wins
2. `$PLUGIN_DATA/stylelatch` — Codex hands plugins a writable data dir
3. `~/.stylelatch` — default

Holds `ACTIVE.md` (the composed rules) and `state.json` (what is on, plus the
per-turn nudge). Writes are atomic, so a hook never reads half a file.

---

## Write your own style

Styles come from three places, most specific first:

| Source | Where | For |
|---|---|---|
| project | `<repo>/.stylelatch/styles/` | The voice a repository agreed on. Commit it. |
| user | `$STYLELATCH_HOME/styles/` | Yours. Survives every plugin update. |
| built-in | `<plugin>/styles/` | Ships with StyleLatch. Replaced on update. |

First source wins on a name or id collision, so putting an `eli5.md` in your
user directory replaces the built-in one everywhere. That is the point. `::?`
lists what was shadowed and by whom, so an override is never a mystery.

Drop a file in `PROFILES/` or `MODIFIERS/` under any of those roots:

```markdown
---
id: "50"
name: your-name
nudge: The 30-word version, injected every turn. Keep it sharp.
---

The full rules. This text lands verbatim in ACTIVE.md.
```

`nudge` is required on profiles, and `::test` fails if one is missing. Write
rules a model can follow rather than a mood it should absorb: *two sentences
maximum* beats *be concise*.

`::?` prints the exact directories, so you never have to guess where to put the
file. Nothing is created for you — an empty directory you did not ask for is
clutter, and `::?` naming the path is enough.

---

## Install

1. Paste the snippet from [AGENTS_SNIPPET.md](AGENTS_SNIPPET.md) into your
   global instructions file. Once, and never again — it names no profile, so
   switching styles never touches it.
2. Install the plugin. The repo carries its own marketplace manifest:

   ```bash
   claude plugin marketplace add 0langa/StyleLatch
   claude plugin install stylelatch@stylelatch-dev
   ```

3. **Codex only:** trust the hooks once in **Settings > Coding > Hooks**.

Then start a new session, and type `::?`.

---

## Tests

```bash
python -m unittest discover -s tests -v
```

They run against a temp directory, never your real `~/.stylelatch`.

See [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request, and
[ROADMAP.md](ROADMAP.md) for where this is going.

## License

MIT.
