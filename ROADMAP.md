# Roadmap

What StyleLatch is aiming at, and the order it gets there. Shipped items move
to `CHANGELOG.md`; this file only ever describes what is still ahead.

## The thesis

An output style is a *continuous* constraint. Nothing in a conversation
re-triggers it, so it decays — usually somewhere around the fifth reply, and
always after a compact. Everything here follows from taking that seriously:

1. Re-inject on a schedule, not once.
2. Make the re-injection cheap enough to afford every single turn.
3. Put the switch where the user already is — in the chat, not in a shell.

## v0.2.0 — one surface

The terminal stops being a user-facing surface. Everything moves to `::`.

- [x] Continuous integration, lint, and repository hygiene.
- [x] Delete `scripts/`. `::` already does everything it did.
- [x] `::test` — one diagnostic entry point, run from chat.
- [x] Debug mode expires on its own — on session change, on a turn budget, and
      on a wall-clock TTL, whichever comes first.
- [x] Forgiving directive parsing, and a "did you mean" for near misses.
- [ ] A skill and a slash command, so the surface is discoverable by somebody
      who does not already know the `::` grammar.
- [ ] Documentation split out of the README.

## v0.3.0 — styles that are yours

Today a style lives inside the plugin, which means an update overwrites it.
That has to stop before anyone invests in writing one.

- [ ] Three style sources, resolved in order: user (`$STYLELATCH_HOME/styles`),
      project (`.stylelatch/styles` in the repo), then the built-ins.
- [ ] A project-scoped latch, so `terse` in one repo does not follow you into
      every other session.
- [ ] Session-scoped and one-shot latches. `::terse!` for exactly this turn.
- [ ] Precedence, stated once and enforced everywhere: session, then project,
      then global.

## v0.4.0 — see what it is doing

Injection is invisible by design, which makes failure invisible too.

- [ ] `::status` — what is latched, where it came from, which scope won, what
      it costs in characters and estimated tokens, and how long it has been on.
- [ ] A bounded latch history, so "what did I have on yesterday" is answerable.
- [ ] Drift instrumentation: how many turns since the last full re-injection.

## v0.5.0 — a plugin, not a script folder

- [ ] A skill that teaches the agent to author and validate a style properly,
      so a user can say "make me a style for code review" and get a good one.
- [ ] Codex parity verified inside a real Codex session, not only by docs.
- [ ] Documentation split out of the README: architecture, authoring, and a
      provider capability matrix.

## Later, and deliberately unscheduled

- Style linting: catch a style that contradicts itself, or that tries to
  govern permissions rather than prose.
- A measured answer to "does this style actually hold", beyond the canary.
- Team styles shared through a repository rather than a home directory.

## Non-goals

- **A user-facing CLI.** Deleted on purpose in v0.2.0. See `CONTRIBUTING.md`.
- **Runtime dependencies.** StyleLatch runs inside someone else's Python.
- **Styles that change what the model may do.** See `SECURITY.md`.
- **Per-turn injection of the full document.** Layer 3 stays about thirty
  words, forever. That budget is the only reason it is affordable at all.
