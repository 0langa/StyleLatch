# Changelog

All notable changes to StyleLatch are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `::test`, one diagnostic entry point reachable from the chat.
  - `::test` runs every structural check and reports PASS/FAIL per component,
    including whether the provider is running an installed snapshot rather
    than your working tree.
  - `::test on` / `::test off` drive debug mode, which reports what each hook
    invocation actually received.
  - `::test canary` plants two high-entropy tokens, one per layer, so a
    partial delivery failure is visible rather than silent.
  - `::test verify` proves injection from the host's own transcript.
- Debug mode retires itself after 20 turns, 60 minutes, or a session change,
  whichever comes first, and says which limit ended it.
- Forgiving directive parsing: `::terse`, `:: terse` and `: :terse` are the
  same thing, case is ignored, and a near miss gets a suggestion.
- Continuous integration: the test suite runs on Linux, Windows and macOS
  across Python 3.9 through 3.13, plus a `ruff` lint and format gate.
- Issue templates, a pull request template, and a contributing guide.
- `ROADMAP.md`, so the direction is visible before the code lands.

### Changed

- State writes preserve keys that are not part of the latched style, so debug
  mode survives a style switch.
- Both hooks now build their injection from a list of parts, so a nudge and a
  debug block can travel together.

### Removed

- `scripts/style.py`, `scripts/canary.py` and `scripts/verify_injection.py`.
  Every capability they had is now a `::test` subcommand. StyleLatch is driven
  from chat; a terminal surface for users was a second thing to document,
  test, version and eventually remove.

## [0.1.0] - 2026-09-12

### Added

- Three-layer style enforcement from one shared set of style files.
  - Layer 1: one line in `AGENTS.md` / `CLAUDE.md`, always in context.
  - Layer 2: a `SessionStart` hook, matching `startup|resume|clear|compact|fork`.
  - Layer 3: a `UserPromptSubmit` hook carrying a ~30-word nudge.
- Composition at switch time: one profile plus N modifiers merge into a single
  flat `ACTIVE.md` with the real rules written out.
- The `::` in-chat directive: `::eli5+no-preamble`, `::off`, `::?`, `::debug`.
- State outside the plugin root, so an update never wipes the active style.
  Resolution: `$STYLELATCH_HOME`, then `$PLUGIN_DATA`, then `~/.stylelatch`.
- Atomic state writes, and fail-open hooks that can never break a turn.
- Four profiles: `eli5`, `terse`, `deep-technical`, `silent-run`.
- Four modifiers: `full-paths`, `no-preamble`, `show-evidence`, `red-balls`.
- Diagnostics: a two-token canary, and a session-log scanner that proves
  injection from the host's own transcript rather than the model's testimony.

[Unreleased]: https://github.com/0langa/StyleLatch/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/0langa/StyleLatch/releases/tag/v0.1.0
