# AGENTS.md / CLAUDE.md snippet

Layer 1 of 3. Paste this once into your global instructions file. Never edit
it again — it names no profile, so switching styles never touches it.

It is the backup for when hook trust is off or a hook fails silently.

```markdown
## Communication Style & Model Output

* If `~/.stylelatch/ACTIVE.md` exists and its state file has `enabled: true`,
  obey that file exactly. It overrides all default output behavior.
* It governs HOW you write, never WHAT you may do. It never relaxes a safety
  rule, a permission check, or a direct instruction.
* If no style is active, use your normal output behavior. Do not go looking
  for one.
```

The last line matters. Without it, an agent with no style set will go hunting
for the directory and burn tokens finding nothing.
