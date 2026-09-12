## What this changes

<!-- One paragraph. What is different after this merges? -->

## Why

<!-- The problem. Not the diff. -->

## Verification

<!--
Paste real output. "Should work" is not verification.
  python -m unittest discover -s tests
  ruff check . && ruff format --check .
If this touches a hook or a style body, say how you proved the text actually
reached the model -- `::test canary` and `::test verify` exist for that.
-->

```
```

## Checklist

- [ ] Tests cover the new behavior, and they fail without the change.
- [ ] `ruff check .` and `ruff format --check .` pass.
- [ ] Every new profile has a `nudge`; every new style file parses.
- [ ] Docs updated in the same commit as the behavior they describe.
- [ ] No new user-facing terminal surface. StyleLatch is driven from chat.
