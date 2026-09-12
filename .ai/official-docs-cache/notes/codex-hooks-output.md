---
provider: codex
topic: hooks-events-and-additional-context
checked_at: 2026-09-12
stability: likely-changing
refresh_after_days: 7
sources:
  - url: https://learn.chatgpt.com/docs/hooks
    title: Codex — Hooks
    note: https://developers.openai.com/codex/hooks now 308-redirects here
claims:
  - Codex supports UserPromptSubmit as a first-class hook event.
  - Codex supports SessionStart, SessionEnd, PreToolUse, PostToolUse, PreCompact, PostCompact, UserPromptSubmit, PermissionRequest, SubagentStart, SubagentStop, Stop, Interrupt.
  - Context injection uses hookSpecificOutput.hookEventName + hookSpecificOutput.additionalContext, added as extra developer context.
  - With plugins enabled, Codex looks for hooks/hooks.json inside the plugin root; a hooks entry in .codex-plugin/plugin.json can override that location.
  - Plugin hook commands receive PLUGIN_ROOT and PLUGIN_DATA env vars; PLUGIN_DATA is a writable data location.
used_by:
  - StyleLatch (hooks/hooks.json, hooks/scripts/_style.py)
---

## Notes

This settles the one assumption the whole 3-layer design rested on: **Codex
does fire `UserPromptSubmit`**, so the per-turn anti-drift nudge is portable
and no Codex-specific fallback is needed.

The output JSON shape is identical to Claude Code's, so one `hooks/hooks.json`
and one pair of scripts serve both providers. Do not declare a `hooks` entry
in the manifest when using the default `hooks/hooks.json` location — on Claude
Code that double-registers and fails plugin load with "Duplicate hooks file".

`PLUGIN_DATA` is the correct home for mutable state on Codex, which is why
`_style.state_dir()` checks it before falling back to `~/.stylelatch`.

Codex additionally requires non-managed hooks to be trusted once in
**Settings > Coding > Hooks** before they run.
