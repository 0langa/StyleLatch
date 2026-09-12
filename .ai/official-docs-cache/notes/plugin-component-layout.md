---
provider: claude-code, codex
topic: plugin-component-layout-skills-commands-manifests
checked_at: 2026-09-12
stability: likely-changing
refresh_after_days: 7
sources:
  - url: https://code.claude.com/docs/en/plugins-reference
    title: Claude Code — Plugins reference
  - url: https://code.claude.com/docs/en/slash-commands
    title: Claude Code — Slash commands
  - url: https://developers.openai.com/plugins/build/plugins
    title: Codex — Build plugins
  - url: https://agent-plugins.org/schemas/1.0.0/plugin.schema.json
    title: Agent Plugins 1.0.0 — plugin manifest schema
claims:
  - Claude Code auto-discovers skills/<name>/SKILL.md and commands/*.md at the plugin root.
  - A `skills` entry in plugin.json ADDS to the default skills/ scan; `commands` and `agents` REPLACE their defaults.
  - Claude Code exposes CLAUDE_PLUGIN_ROOT, CLAUDE_PLUGIN_DATA and CLAUDE_PROJECT_DIR to hook commands.
  - A Claude Code slash command runs shell with the !`<command>` form, and `allowed-tools` pre-approves it.
  - Codex reads a portable root plugin.json ($schema agent-plugins.org/schemas/1.0.0), with .codex-plugin/plugin.json as a legacy fallback overlay.
  - Codex auto-discovers skills/ and mcp.json, and optionally hooks/hooks.json.
  - Codex hook commands receive PLUGIN_ROOT and PLUGIN_DATA, plus CLAUDE_PLUGIN_ROOT and CLAUDE_PLUGIN_DATA as compatibility aliases.
  - The portable manifest requires only $schema and name; author is an object of name/email/url; no properties outside the schema are permitted at the root.
used_by:
  - StyleLatch (plugin.json, .claude-plugin/, .codex-plugin/, skills/, commands/)
---

## Notes

The important find is that **one `skills/<name>/SKILL.md` serves both hosts**.
No per-provider skill directory is needed, and neither manifest has to declare
it.

`CLAUDE_PLUGIN_DATA` is documented, not speculative. `_style.state_dir()` had
been checking it on the assumption that it might exist one day; it does, and
Codex aliases it to `PLUGIN_DATA`. The docstring was corrected to match.

`CLAUDE_PROJECT_DIR` is new to StyleLatch and is now the second choice for
project detection, behind the `cwd` the hook payload carries — the payload is
per-invocation and therefore more precise.

Negative finding, and the reason for a test: the portable schema permits **no
additional properties at the root**. A stray field in `plugin.json` is not
ignored, it is invalid. Client-specific data belongs under
`extensions.<reverse.domain>`.

Carried forward from `codex-hooks-output.md`: do not declare a `hooks` path in
any manifest while using the default `hooks/hooks.json` location. On Claude
Code that double-registers and fails plugin load with "Duplicate hooks file".
