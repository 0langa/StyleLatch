---
provider: claude-code
topic: hooks-sessionstart-matchers-and-additional-context
checked_at: 2026-09-12
stability: likely-changing
refresh_after_days: 7
sources:
  - url: https://code.claude.com/docs/en/hooks
    title: Claude Code — Hooks reference
    note: https://docs.claude.com/en/docs/claude-code/hooks now 301-redirects here
claims:
  - SessionStart matcher values are startup, resume, clear, compact and fork.
  - SessionStart and UserPromptSubmit both support hookSpecificOutput.additionalContext.
  - Universal JSON output fields include systemMessage, terminalSequence and additionalContext.
  - UserPromptSubmit does not support permissionDecision; that field is for tool events.
  - Only SessionStart hooks can receive a model field in their input payload.
used_by:
  - StyleLatch (hooks/hooks.json)
---

## Notes

`fork` is the important matcher here and is easy to miss. The user's whole
switching model is "change the style, then fork the chat" — without `fork` in
the matcher the new style would not load on the fork.

RECALL (this user's other plugin) ships `startup|resume|compact` only. That
predates or overlooks `clear` and `fork`. Worth a follow-up there.

Negative finding: the docs page does **not** print a verbatim
`hookSpecificOutput` example for either SessionStart or UserPromptSubmit. The
exact shape used here is taken from RECALL's `hooks/scripts/hook_io.py`
(`additional_context()`), which is verified working on both providers, and is
corroborated by the Codex hooks page which does print it verbatim.
