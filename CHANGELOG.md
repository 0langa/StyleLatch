# Changelog

All notable changes to StyleLatch are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- A guard that reviews every style for language governing *conduct* rather
  than *prose* — skipping a confirmation, reporting a pass that did not happen,
  overriding the operator's instructions, relaxing a safety rule. `::test`
  reports it, and latching such a style prints the same warning.

  It warns and never blocks: the model's own training is the real defence, and
  refusing on a regular expression would produce false confidence. It is tuned
  against false positives rather than for coverage, because a warning that
  fires on a reasonable style teaches people to ignore warnings. CI asserts
  that no style StyleLatch ships trips its own guard.

## [0.3.0] - 2026-09-12

### Added

- **A fourth layer, and the first one that reads rather than writes.** A style
  may declare machine-checkable assertions in its frontmatter, and a `Stop`
  hook measures the finished reply against them:

  ```yaml
  checks: max_sentence_words=25; forbid=let me know if; no_bullets
  ```

  Rules: `max_sentence_words`, `max_reply_lines`, `max_reply_chars`,
  `max_paragraphs`, `forbid`, `forbid_opening`, `require`, `no_headings`,
  `no_bullets`. Modifiers can add checks, and they accumulate.
- **Closed-loop correction.** Breaking a check puts one short line in the next
  turn's nudge naming the rule that broke, instead of restating the whole
  style. Naming the specific failure is a stronger signal for fewer tokens.
  Each breach is delivered exactly once, so a host without a `Stop` hook cannot
  nag forever about one old reply.
- `::status` reports adherence over the recent replies, and what broke.
- `::test` fails on a `checks` line it cannot parse. A check that is silently
  never enforced is the worst outcome: the style looks measured and is not.
- The five built-in styles that have mechanically checkable rules now declare
  them, so this works without writing a style first.
- One-shot latches: `::terse! explain this regex` applies the rules to that
  message and latches nothing, so trying a style — or asking for one plain
  answer — no longer costs you the style you actually work in.
- A bounded record of what was latched and when. `::status` shows the last
  five, so "what did I switch away from" is answerable.

## [0.2.1] - 2026-09-12

### Fixed

- The slash command is now `/styles`, not `/stylelatch`. Claude Code lists
  skills and commands in one inventory, so shipping `skills/stylelatch`
  alongside `commands/stylelatch.md` registered two components under the same
  invocation name and one shadowed the other in the `/` menu. A test now
  refuses any command that shares a name with a skill.

## [0.2.0] - 2026-09-12

### Added

- A skill at `skills/stylelatch/`, auto-discovered by both Claude Code and
  Codex, so an agent can help you write and validate a style of your own
  rather than only wear one.
- A `/stylelatch` slash command on Claude Code, for people browsing the `/`
  menu who have not met the `::` grammar yet.
- A portable `plugin.json` following the Agent Plugins 1.0.0 spec, alongside
  the two provider manifests. A test keeps all three in agreement.
- `docs/architecture.md`, `docs/authoring-styles.md` and `docs/providers.md`.
- `CLAUDE_PROJECT_DIR` is used as a second source for project detection, behind
  the working directory the hook payload carries.
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

[Unreleased]: https://github.com/0langa/StyleLatch/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/0langa/StyleLatch/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/0langa/StyleLatch/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/0langa/StyleLatch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/0langa/StyleLatch/releases/tag/v0.1.0
