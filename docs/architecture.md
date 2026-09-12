# Architecture

StyleLatch is about three hundred lines of stdlib Python and a directory of
Markdown. Everything in it follows from one observation.

## The problem

An output style is a **continuous** constraint. Unlike a task instruction —
which is satisfied once and then done — it governs every sentence, forever, and
nothing in the conversation ever re-triggers it.

So attention to it falls off. In practice the shape is:

- turns 1–4: obeyed,
- turns 5–10: partly obeyed, usually losing the negative rules first ("no
  preamble" goes before "short sentences"),
- after a compact: gone entirely, because the instruction was in the part of
  the context that got summarised away.

Anything that fixes this has to re-state the constraint on a schedule. The rest
of the design is about making that affordable.

## Four layers

| Layer | Mechanism | Fires | Carries |
|---|---|---|---|
| 1 | a line in `AGENTS.md` / `CLAUDE.md` | always in context | a pointer to `ACTIVE.md` |
| 2 | `SessionStart` hook | startup, resume, clear, compact, fork | the whole contract |
| 3 | `UserPromptSubmit` hook | every turn | ~30 words, plus a correction |
| 4 | `Stop` hook | after every reply | nothing — it *reads* |

**Layer 2** is the load-bearing one. Its matcher includes `compact` and `fork`,
which are exactly the two moments a style dies otherwise.

**Layer 3** is what stops the decay between session starts. It is only
affordable because it is small: `MAX_NUDGE_CHARS` is 300, and the nudge is not
a summary of the style but the two or three rules that decay first.

**Layer 1** is the fallback for when hooks are untrusted (Codex requires a
one-time trust step) or silently broken. It reads `ACTIVE.md` straight off
disk. It cannot resolve a scope, which is why `ACTIVE.md` is a mirror rather
than the source of truth.

**Layer 4** is the only one that reads rather than writes. It pulls the reply
that just finished out of the host's own transcript and checks it against the
style's declared assertions. That is what turns "the style is holding" from an
impression into a number, and it is what lets layer 3 stop being a reminder and
start being a correction:

```
OUTPUT STYLE 02 ACTIVE — obey it exactly. Answer first, in one line. …
STYLE BREACH last reply: wrote "let me know if"; wrote "hope that helps".
Do not repeat it in this one.
```

Naming the rule that just broke is a far stronger signal than restating the
whole style, and it is cheaper.

When nothing is latched, every hook prints `{"continue": true}` and stops. The
cost of having StyleLatch installed and unused is two short-lived process
spawns per exchange, both of which exit after reading one small JSON file.

## Compose at switch time, not read time

A latch names a **recipe**: one profile and any number of modifiers. When it is
resolved, those files are merged into one flat document with the real rules
written out, and that document is what the model sees.

The alternative — telling the model "you are in style 02, read
`styles/PROFILES/02-terse.md`" — costs a tool call, and more importantly costs
a hop that can be dropped. Every hop is a chance for the constraint to not
arrive.

```
    profile + modifiers  ──compose──▶  one flat document  ──inject──▶  model
         (the recipe)                     (ACTIVE.md)
```

## State

State lives **outside** the plugin directory, because a plugin update replaces
that directory wholesale. Resolution order:

1. `$STYLELATCH_HOME` — explicit override
2. `$PLUGIN_DATA/stylelatch` or `$CLAUDE_PLUGIN_DATA/stylelatch` — the
   providers' own writable per-plugin directory
3. `~/.stylelatch`

`state.json` is versioned and migrates itself forward on read. It holds:

```json
{
  "version": 2,
  "latches": {
    "session": { "<session id>": { "profile": "...", "modifiers": [], "at": 0 } },
    "project": { "<normalised path>": { "...": "..." } },
    "global":  { "*": { "...": "..." } }
  },
  "enabled": true, "scope": "project", "label": "02", "nudge": "...",
  "debug": { "...": "..." }
}
```

The `latches` block is the truth. Everything beside it is a **mirror** of
whichever latch currently wins, refreshed by the hooks, and exists for layer 1.

Writes go through a temp file and a rename, so a reader never sees half a file.

## Scopes

Three, resolved most specific first: **session**, **project**, **global**.

A project is found by walking up from the working directory the host reports,
looking for `.git`, `.hg`, `.jj`, `.svn`, or `.stylelatch/styles`. The walk
stops at the home directory, because `~/.stylelatch` is the default state
directory and would otherwise make home a project.

A scope whose key cannot be determined — no project found, or no session id
from the host — is **refused**, not stored. A latch under an empty key can
never be read back, so the user would be told "latched" and then watch nothing
happen.

## Style sources

Three, also resolved most specific first:

| Source | Path | Replaced by an update? |
|---|---|---|
| project | `<repo>/.stylelatch/styles/` | no |
| user | `$STYLELATCH_HOME/styles/` | no |
| built-in | `<plugin>/styles/` | yes |

First source wins on a name or id collision. A losing entry is not dropped from
the catalogue: it keeps a `shadowed_by` pointer, so `::?` and `::test` can say
which source won and which lost.

## Measuring adherence

A style may declare machine-checkable assertions in its frontmatter:

```yaml
checks: max_sentence_words=25; forbid=let me know if; no_bullets
```

Layer 4 evaluates them against the finished reply and records the result,
bounded to the last twenty turns. Three deliberate limits:

- **Only mechanical rules.** "Name the mechanism, not the vibe" is not
  checkable and is not meant to be. What *is* checkable turns out to cover most
  real decay, because drift is usually additive: the preamble returns, the
  closing offer of help returns, the bullet list grows a summary.
- **Code is not prose.** Fenced and inline code is stripped before prose rules
  run. A rule about sentence length is not talking about a shell command.
- **Each breach is corrected once.** If the Stop hook is not running — an
  unsupported host, an unrecognised transcript shape — the last record never
  changes, and a correction that repeated every turn would be nagging about a
  reply the user moved past long ago.

A reply the module cannot find in the transcript records **nothing**. Recording
a clean turn there would be a lie, and a broken one worse.

## Fail open, always

Every hook entrypoint catches everything and falls back to
`{"continue": true}`. A corrupt state file means "no style", not a crash. An
unreadable style file is skipped, not fatal. A latch pointing at a style that
was deleted injects nothing rather than half a contract.

This is not defensive habit. A hook runs inside somebody else's process, on
every turn of their work. The worst acceptable failure is that StyleLatch stops
having an opinion.

## Module map

```
hooks/scripts/
  _style.py              paths, style files, compose, scopes, state    (the model)
  _directives.py         parsing and dispatch for ::                   (the controller)
  _diagnostics.py        self-test, status, debug mode, canary, verify
  _adherence.py          the check language, evaluation, and the record
  session_start.py       layer 2 entrypoint
  user_prompt_submit.py  layer 3 entrypoint
  stop.py                layer 4 entrypoint
  _show.py               renders the catalogue for the slash command
```

`_style.py` knows nothing about `::`. `_directives.py` produces only text.
Neither imports anything outside the standard library.
