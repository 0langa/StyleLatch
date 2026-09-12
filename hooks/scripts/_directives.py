"""The `::` directive -- StyleLatch's only user-facing surface.

Typing `::eli5+no-preamble` into the chat latches that style and applies it to
the very message it was typed in. No terminal, no restart, no model in the
loop: a regular expression and a file write, inside the hook that was going to
run anyway.

Why `::` and not something friendlier. `/` is slash-command territory in both
Claude Code and Codex, and `#` is Claude Code's add-to-memory shortcut. The
host would eat either before a hook ever saw it. `::` is claimed by nobody and
almost never opens a sentence.

The grammar is deliberately forgiving. Somebody who half-remembers the syntax
at the moment they need it should still land on something that works, and the
cost of being generous here is a slightly wider regular expression.
"""

from __future__ import annotations

import difflib
from typing import Any

import _diagnostics
import _style

# Alias sets. Being generous here costs one tuple and saves a user who
# half-remembers the word from getting nothing back.
CATALOG_WORDS = ("?", "help", "list", "styles", "h")
OFF_WORDS = ("off", "none", "stop", "clear")
TEST_WORDS = ("test", "testlatch", "debug", "diag", "doctor", "selftest")


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------


def catalog_text() -> str:
    lines = ["StyleLatch", "", "PROFILES (pick one)"]
    for entry in _style.unique(_style.profiles()):
        lines.append(f"  {entry['id']:>3}  {entry['name']:<16}{_summarize(entry['nudge'])}")
    lines += ["", "MODIFIERS (stack with +)"]
    for entry in _style.unique(_style.modifiers()):
        lines.append(f"  {entry['id']:>3}  {entry['name']:<16}{_summarize(entry['nudge'])}")

    state = _style.load_state()
    lines += [
        "",
        f"Latched now: {state.get('label', 'nothing') if state.get('enabled') else 'nothing'}",
        "",
        "  ::terse                 latch a profile",
        "  ::eli5+no-preamble      stack modifiers onto it",
        "  ::01+02                 ids work too",
        "  ::terse fix the parser  latch it and do the task in one message",
        "  ::off                   back to default behaviour",
        "  ::test                  check StyleLatch itself",
        "  ::?                     this list",
    ]
    return "\n".join(lines)


def _summarize(nudge: str, width: int = 54) -> str:
    text = " ".join(nudge.split())
    return text if len(text) <= width else text[: width - 1].rstrip() + "…"


def test_help() -> str:
    return "\n".join(
        [
            "StyleLatch diagnostics",
            "",
            "  ::test          run every structural check and report",
            "  ::test on       debug mode: what each hook receives, every turn",
            "  ::test off      end debug mode now",
            "  ::test canary   plant two high-entropy tokens and prove delivery",
            "  ::test verify   search the host's own transcript for the injection",
            "",
            "Debug mode ends by itself after "
            f"{_diagnostics.DEBUG_TURNS} turns, "
            f"{_diagnostics.DEBUG_SECONDS // 60} minutes, or when the session changes.",
        ]
    )


# --------------------------------------------------------------------------
# parsing
# --------------------------------------------------------------------------


def parse(prompt: str) -> tuple[str, str] | None:
    """Return (token, rest) when the message opens with a directive, else None."""
    if not prompt:
        return None

    head = prompt.lstrip(" \t")
    consumed = 0
    colons = 0
    for char in head:
        if char == ":":
            colons += 1
            consumed += 1
            if colons == 2:
                break
        elif char in " \t" and colons == 1:
            consumed += 1
        else:
            return None
    if colons != 2:
        return None

    body = head[consumed:].lstrip(" \t")
    token_chars = []
    for char in body:
        if char.isalnum() or char in "_+-?":
            token_chars.append(char)
        else:
            break
    token = "".join(token_chars)
    if not token:
        return None
    return token.lower(), body[len(token) :].strip()


def suggest(unknown: str) -> str:
    """Offer the closest real style name for a near miss."""
    names = {entry["name"] for entry in _style.unique(_style.profiles())}
    names |= {entry["name"] for entry in _style.unique(_style.modifiers())}
    names |= set(CATALOG_WORDS) | set(OFF_WORDS) | {"test"}
    close = difflib.get_close_matches(unknown.lower(), sorted(names), n=2, cutoff=0.6)
    if not close:
        return ""
    if len(close) == 1:
        return f"Did you mean ::{close[0]} ?"
    return f"Did you mean ::{close[0]} or ::{close[1]} ?"


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------


def _only_this(bare: bool) -> str:
    """Tell the model to report and stop when the message carried no task."""
    if not bare:
        return ""
    return (
        "\n\nThe user sent only this directive, with no task attached. Show "
        "them the text above, in a code fence, and write nothing else."
    )


def _handle_test(rest: str, payload: dict[str, Any]) -> str:
    word, _, tail = rest.partition(" ")
    word = word.strip().lower()
    tail = tail.strip()

    if word == "on":
        return _diagnostics.start_debug(payload) + _only_this(True)
    if word == "off":
        return _diagnostics.stop_debug() + _only_this(True)
    if word == "canary":
        return _diagnostics.arm_canary() + _only_this(True)
    if word == "verify":
        return _diagnostics.verify_injection(payload, tail) + _only_this(True)
    if word in ("?", "help"):
        return test_help() + _only_this(True)

    # Anything else after ::test is the user's actual request, not a
    # subcommand. Run the default report and let the task through.
    report = _diagnostics.self_test(payload)
    return report + _only_this(not rest)


def apply(token: str, rest: str, payload: dict[str, Any]) -> str:
    """Run a directive and return the text to inject. Never raises."""
    bare = not rest

    if token in CATALOG_WORDS:
        return catalog_text() + _only_this(bare)

    if token in OFF_WORDS:
        _style.disable()
        return "StyleLatch: off. Default output behaviour from here on." + _only_this(bare)

    if token in TEST_WORDS:
        return _handle_test(rest, payload)

    parts = [part for part in token.split("+") if part]
    try:
        result = _style.compose(parts[0], parts[1:])
    except (KeyError, IndexError):
        hint = suggest(parts[0] if parts else token)
        head = f"StyleLatch: no style called '{token}'. Nothing changed."
        if hint:
            head += " " + hint
        return head + "\n\n" + catalog_text() + _only_this(bare)

    _style.write_state(result)
    summary = f"StyleLatch: latched {result['label']} ({result['profile']})"
    if result["modifiers"]:
        summary += " + " + ", ".join(result["modifiers"])

    if bare:
        return (
            f"{summary}. It is in force from this message on.\n\n"
            f"{result['document']}\n"
            "The user sent only a switch, no task. Reply with exactly "
            f'"latched: {result["label"]}" and nothing else.'
        )
    return (
        f"{summary}. It is in force from this message on. Apply it to the rest "
        "of this very message, which is the user's actual request.\n\n"
        f"{result['document']}"
    )
