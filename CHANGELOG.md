# Changelog

All notable changes to StyleLatch are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet.

## [0.3.2] - 2026-10-15

### Upgrading

- **Your styles now live in `~/.stylelatch/styles`**, or in
  `$STYLELATCH_HOME/styles` when that is set, and never in the host's plugin
  data directory. The first hook run after updating copies them there from
  the old plugin data directory. Edit them in the new place from now on: the
  old copies stay where they were, but StyleLatch no longer loads styles from
  them. If `::test` lists files kept aside in `styles-from-plugin-data/`,
  compare them with the copies in your style directory and keep the one you
  want.
- **No new hook trust step in Codex.** The hook definitions are the same as
  in 0.3.1, so there is nothing to trust again if you trusted 0.3.1's hooks.
  Coming from 0.3.0 or earlier, trust them in `/hooks` as described under
  0.3.1.

### Fixed

- **Your own styles survive an uninstall.** Under a plugin install the user
  style directory sat in the host's plugin data directory, which Claude Code
  deletes when the plugin is uninstalled. User styles now always live in
  `$STYLELATCH_HOME/styles`, or `~/.stylelatch/styles` when that is not set.
  Runtime state (the latch, `ACTIVE.md`) stays where it was.
- Styles already in a plugin data directory are copied to the user directory
  on first use. Nothing is deleted or overwritten. A file that the user
  directory already holds with other content is kept aside in
  `styles-from-plugin-data/` beside it and listed by `::test`. A ledger
  next to the old styles makes later runs copy only what changed since.

## [0.3.1] - 2026-10-14

### Upgrading

- **Codex users must trust the hooks again.** All three hook commands changed,
  and Codex skips a new or changed hook until it is trusted. After updating,
  run `/hooks` and trust StyleLatch's hooks. Until you do, they do not run at
  all.
- **Claude Code on Windows** needs two things for the hooks to run: Git for
  Windows, because Claude Code runs hooks through Git Bash, and a Python 3
  that starts as `py -3` or `python`. The Microsoft Store alias does not
  count.

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

### Fixed

- No hook ever ran under Claude Code on Windows. Claude Code runs a hook's
  `command` through Git Bash and does not read `commandWindows`, which only
  Codex honours, and on Windows `python3` is usually the Microsoft Store alias
  that prints *Python was not found*. The command now picks `py -3`, or
  `python`, on Windows and keeps `python3` everywhere else.
- The `Stop` hook measured the wrong reply. It read only the transcript, which
  Claude Code documents as not guaranteed to hold the final message yet when
  `Stop` fires, and it took a tool call's input as prose, so a `Write` of a
  Markdown file could be recorded as a breach. It now uses the
  `last_assistant_message` field both hosts send, and the transcript fallback
  skips tool calls.
- `::test canary off` with no canary armed cleared the real global latch while
  reporting that nothing changed. It now only ever removes the canary.
- Disarming the canary put back only the latch that had been winning. Arming
  stands down the session and project latches and takes over the global one,
  so the other two were lost, and re-arming while a more specific latch won
  replaced the snapshot and lost the original global latch too. Every latch it
  displaced now comes back, re-arm or not, unless a newer one was set while the
  canary was armed.
- The conduct guard never read a style's `nudge`, which is the one part
  injected on every turn. It reads it now.
- The conduct guard flagged styles that restate the boundary, such as *never
  skip the confirmation*, *do not claim the tests passed unless you ran them*
  or *never hide errors*, and matched inside words (*chide the error*). A
  negation sitting right on the phrase now clears it; one on another verb, as
  in *don't hesitate to skip the confirmation*, still does not.
- A style file saved as UTF-8 with a byte order mark, which is what Windows
  PowerShell 5.1 writes, lost its whole frontmatter: no nudge, no checks, and
  the frontmatter injected as part of the body. It parses now.
- With two sessions open, a breach in one was corrected in the other. Every
  session wearing a latch writes to one adherence record, and the next prompt
  in any session took the newest entry. Corrections now go to the session
  whose reply broke the rule, and the `Stop` hook resolves that session's own
  latch before measuring instead of trusting whichever session ran last.
- On Windows a state write failed whenever another process had `state.json`
  open, which another session's hook reading it is enough for, and the hook
  then dropped the turn's directive silently. A refused replace is now retried
  briefly, and every write uses its own temp file, so two hooks writing at
  once can no longer rename each other's half-written file into place.

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

[Unreleased]: https://github.com/0langa/StyleLatch/compare/v0.3.2...HEAD
[0.3.2]: https://github.com/0langa/StyleLatch/compare/v0.3.1...v0.3.2
[0.3.1]: https://github.com/0langa/StyleLatch/compare/v0.3.0...v0.3.1
[0.3.0]: https://github.com/0langa/StyleLatch/compare/v0.2.1...v0.3.0
[0.2.1]: https://github.com/0langa/StyleLatch/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/0langa/StyleLatch/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/0langa/StyleLatch/releases/tag/v0.1.0
