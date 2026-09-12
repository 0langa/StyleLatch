# Contributing to StyleLatch

## The one rule that shapes everything else

**StyleLatch is driven from chat, not from a terminal.**

Anything a *user* needs to do — switch a style, inspect state, diagnose a
failure — happens by typing a `::` directive into Claude Code or Codex. The
terminal exists for people *developing* StyleLatch, and for nobody else. A
pull request that adds a user-facing CLI will be turned down, however
convenient it feels, because every terminal surface is a second thing to
document, test, version and eventually remove.

## Getting set up

No dependencies. No virtualenv needed. Python 3.9 or newer.

```bash
git clone https://github.com/0langa/StyleLatch
cd StyleLatch
python -m unittest discover -s tests -v
```

Optional, and what CI enforces:

```bash
ruff check .
ruff format --check .
```

To run StyleLatch against a provider while you work on it, install the repo
as a local plugin. It carries its own marketplace manifest:

```bash
claude plugin marketplace add /path/to/StyleLatch
claude plugin install stylelatch@stylelatch-dev
```

The installed copy is a snapshot, not a link. After changing anything under
`hooks/` or `styles/`, run `claude plugin update stylelatch@stylelatch-dev`
and start a new session.

## What good looks like here

**Hooks fail open, always.** A broken style must never break a turn. Every
hook entrypoint catches everything and falls back to `{"continue": true}`. If
you add a code path that can raise, prove that the fallback still holds.

**Layer 3 stays tiny.** The per-turn nudge is affordable only because it is
about thirty words. `MAX_NUDGE_CHARS` is a budget, not a suggestion. Anything
that needs more room belongs in the layer 2 document.

**Compose at switch time, never at read time.** The agent reads one flat file
with the real rules already written out. It must never have to resolve an id
to a path, follow a reference, or merge anything itself.

**Stdlib only.** No third-party imports in `hooks/` or `styles/`. StyleLatch
runs inside somebody else's Python, on a machine you cannot see.

**Evidence over assertion.** "Should work" is not verification. The repo ships
`::test canary` and `::test verify` precisely because a model's account of its
own context is not evidence.

## Adding a style

A style you are writing for yourself belongs in `$STYLELATCH_HOME/styles/`, and
one for a single repository belongs in that repository's `.stylelatch/styles/`.
Neither needs a pull request. Send one here only for a style that earns its
place as a **built-in**: broadly useful, and not a personal preference.

Drop the file into `styles/PROFILES/` or `styles/MODIFIERS/`:

```markdown
---
id: "07"
name: your-name
nudge: The thirty-word version, injected every turn. This is the hard part.
---

The full rules. This text lands verbatim in the composed document.
```

- `id` must be unique within its directory. The tests enforce it.
- `nudge` is required on profiles. The tests enforce that too.
- Write the body as rules the model can follow, not as a description of a
  vibe. "Two sentences maximum" beats "be concise".
- Read `SECURITY.md` first. A style governs how the model writes. It never
  governs what the model is permitted to do.

## Commits and pull requests

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/):
`feat:`, `fix:`, `docs:`, `test:`, `refactor:`, `chore:`. The subject says what
changed; the body says why it needed to.

Pull requests need real output in the verification section. The template asks
for it because it is the part people skip.
