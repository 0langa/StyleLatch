# Security

## Reporting

Report a vulnerability through
[GitHub private vulnerability reporting](https://github.com/0langa/StyleLatch/security/advisories/new).
Please do not open a public issue for anything exploitable.

## Threat model

StyleLatch injects text into a model's context on every session start and
every turn. That is its entire job, and it is also its entire risk surface.

**What a style may do.** Govern *how* the model writes: length, structure,
vocabulary, ordering, what to include and what to leave out.

**What a style may never do.** Change *what* the model is allowed to do. The
composed document opens with a header stating exactly that, and it is the
reason the header is not configurable. A style that tries to relax a safety
rule, suppress a permission prompt, or override a direct user instruction is a
bug in that style, and a pull request adding one will be rejected.

Concretely, StyleLatch will not accept a built-in style that:

- tells the model to skip confirmations for destructive or outward-facing acts,
- tells the model to conceal errors, failures, or what it did not verify,
- tells the model to claim work is done or verified without evidence,
- attempts to rewrite the model's identity, operator instructions, or tooling
  permissions rather than its prose.

`silent-run` is the edge case worth naming: it suppresses *narration*, and it
says so explicitly — it never suppresses a required confirmation, a hard
blocker, or an unauthorized destructive action.

## The guard

`::test` reviews every style file it can see for language that reads like an
instruction about *conduct* rather than *prose* — skipping a confirmation,
reporting a pass that did not happen, overriding the operator's instructions,
relaxing a safety rule. Latching such a style prints the same warning.

Two things it deliberately is not:

- **It does not block.** The model's own training is the real defence; a
  substring search is a hint. Refusing on a regular expression would produce
  false confidence and would eventually reject somebody's legitimate style.
- **It is tuned against false positives, not for coverage.** A warning that
  fires on a reasonable style teaches people to ignore warnings, and then the
  mechanism is worth nothing. "Without asking" is not a pattern; "without
  asking for permission" is. `tests/test_guard.py` holds a list of innocent
  prose rules that must never trip it, and that list is the real test.

CI asserts that no style shipped with StyleLatch trips its own guard.

## Trust boundaries

- Style files are executable prose. Treat a third-party style the way you
  would treat a third-party shell script: read it before you latch it. A style
  can arrive by cloning a repository with a `.stylelatch/` directory in it,
  which is exactly why the guard speaks up at latch time.
- State lives outside the plugin root and is plain JSON and Markdown owned by
  the invoking user. StyleLatch never writes outside its state directory.
- Hooks are stdlib-only Python with no network access and no subprocess calls.
- Hooks fail open. A crash, a corrupt state file, or an unreadable style
  prints `{"continue": true}` and the turn proceeds with default behavior.
