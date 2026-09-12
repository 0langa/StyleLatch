---
name: styles
description: Show every StyleLatch style, what is latched right now, and the :: directives that switch it.
allowed-tools: Bash(python3 -S *), Bash(py -3 -S *)
disable-model-invocation: true
---

## StyleLatch

!`python3 -S "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_show.py" 2>/dev/null || py -3 -S "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/_show.py"`

## Instructions

Print the block above verbatim inside a code fence. Then add exactly one line
of your own: that a style is switched by typing a directive such as `::terse`
at the start of a message, and that `::test` checks StyleLatch itself when a
style is not applying.

Write nothing else. Do not latch a style on the user's behalf — a directive
only takes effect when it opens the user's own message.
