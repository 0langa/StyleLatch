# Changelog

All notable changes to StyleLatch are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Scoped latches. A latch belongs to a session, a project, or everything, and
  the most specific one that is set wins. `::terse @project` keeps a voice
  inside one repository; `::silent-run @session` dies with the conversation.
- `::off @project` clears one scope and says what takes over; `::off` still
  stops everything.
- Setting a latch that a more specific scope already outranks says so, instead
  of leaving the user to wonder why nothing changed.
- A scope whose key cannot be determined — no project detected, or no session
  id from the host — is refused rather than stored under a key nothing could
  look up again.
- `::status`: what is latched, in which scope, how long ago, and what each
  layer costs in characters and estimated tokens.
- `::test canary off` removes the canary and restores the latch it displaced.
- Styles now come from three sources, most specific first: a project's
  `.stylelatch/styles/`, the user's `$STYLELATCH_HOME/styles/`, and the
  built-ins. A style you write survives a plugin update, and a repository can
  carry the voice its contributors agreed on.
- A shadowed style is reported rather than hidden. `::?` and `::test` both say
  which source won and which one lost.
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

- The state file is versioned and migrates itself forward. A v1 file, which
  carried one unscoped latch, becomes the global latch.
- `state.json` stores the recipe rather than the rendered style, and the hooks
  recompose from it. `ACTIVE.md` became a mirror of the winning latch, which
  is what layer 1 needs and all it can use.
- The canary is a real style file in the user directory rather than a document
  composed in memory, so it goes through exactly the machinery it is testing.
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
