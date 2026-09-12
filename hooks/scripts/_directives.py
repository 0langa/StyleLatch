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
STATUS_WORDS = ("status", "state", "now", "what")


# --------------------------------------------------------------------------
# text
# --------------------------------------------------------------------------


def _row(entry: dict) -> str:
    # Only a style that did not come with the plugin gets a source marker, so
    # the common case stays quiet and an override is impossible to miss.
    mark = "" if entry["source"] == "built-in" else f"[{entry['source']}] "
    return f"  {entry['id']:>3}  {entry['name']:<16}{mark}{_summarize(entry['nudge'])}"


def catalog_text() -> str:
    lines = ["StyleLatch", "", "PROFILES (pick one)"]
    lines += [_row(entry) for entry in _style.unique(_style.profiles())]
    lines += ["", "MODIFIERS (stack with +)"]
    lines += [_row(entry) for entry in _style.unique(_style.modifiers())]

    state = _style.load_state()
    lines += [
        "",
        f"Latched now: {state.get('label', 'nothing') if state.get('enabled') else 'nothing'}",
        "",
        "  ::terse                 latch a profile, everywhere",
        "  ::eli5+no-preamble      stack modifiers onto it",
        "  ::01+02                 ids work too",
        "  ::terse fix the parser  latch it and do the task in one message",
        "  ::terse! just this one  apply it to this message only, latch nothing",
        "  ::terse @project        only in this repository",
        "  ::terse @session        only in this conversation",
        "  ::off                   back to default behaviour",
        "  ::off @project          drop just the project latch",
        "  ::status                what is latched, where, and what it costs",
        "  ::test                  check StyleLatch itself",
        "  ::?                     this list",
    ]

    shadowed = [
        entry
        for kind in ("PROFILES", "MODIFIERS")
        for entry in _style.collect(kind)
        if entry["shadowed_by"] is not None
    ]
    if shadowed:
        lines += ["", "SHADOWED (a more specific source won)"]
        for entry in shadowed:
            winner = entry["shadowed_by"]
            lines.append(
                f"  {entry['name']} from {entry['source']} is hidden by the {winner['source']} one"
            )

    lines += ["", "Styles are read from, most specific first:"]
    for source, root in _style.style_roots():
        count = len(list((root / "PROFILES").glob("*.md"))) if (root / "PROFILES").is_dir() else 0
        count += (
            len(list((root / "MODIFIERS").glob("*.md"))) if (root / "MODIFIERS").is_dir() else 0
        )
        lines.append(f"  {source:<9} {root}  ({count or 'empty'})")
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
            "  ::test canary off   remove it and restore what was latched before",
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
        elif char == "!" and token_chars:
            # A trailing "!" means "this turn only". It closes the token.
            token_chars.append(char)
            break
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
        if tail.lower() in ("off", "clean", "stop"):
            return _diagnostics.clear_canary() + _only_this(True)
        return _diagnostics.arm_canary() + _only_this(True)
    if word == "verify":
        return _diagnostics.verify_injection(payload, tail) + _only_this(True)
    if word in ("?", "help"):
        return test_help() + _only_this(True)

    # Anything else after ::test is the user's actual request, not a
    # subcommand. Run the default report and let the task through.
    report = _diagnostics.self_test(payload)
    return report + _only_this(not rest)


# --------------------------------------------------------------------------
# scope
# --------------------------------------------------------------------------
#
# "::terse @project" reads as one thought, and "@" cannot start a style name,
# so the scope word is unambiguous without needing a flag character nobody
# would remember. Global stays the default: it is what "I write like this"
# means, and it is what every existing latch already meant.

SCOPE_WORDS = {
    "session": "session",
    "now": "session",
    "chat": "session",
    "project": "project",
    "here": "project",
    "repo": "project",
    "global": "global",
    "everywhere": "global",
    "always": "global",
}

SCOPE_PHRASE = {
    "session": "for this session only",
    "project": "for this project",
    "global": "everywhere",
}


def split_scope(rest: str) -> tuple[str, str, str]:
    """Pull a leading "@word" off the rest. Returns (scope, remainder, bad)."""
    if not rest.startswith("@"):
        return "", rest, ""
    word, _, tail = rest[1:].partition(" ")
    key = word.strip().lower()
    if key not in SCOPE_WORDS:
        return "", tail.strip(), key
    return SCOPE_WORDS[key], tail.strip(), ""


def _scope_problem(bad: str) -> str:
    known = ", ".join(f"@{word}" for word in sorted(set(SCOPE_WORDS)))
    return f"StyleLatch: no scope called '@{bad}'. Nothing changed.\n  scopes: {known}"


def _unaddressable(scope: str) -> str:
    """Refuse a scope whose key cannot be determined for this invocation.

    Storing a latch under an empty key would write state that can never be
    read back: the user would see "latched" and then nothing happening.
    """
    if _style.scope_key(scope):
        return ""
    if scope == "session":
        return (
            "StyleLatch: this host did not send a session id, so a session "
            "latch could never be matched back to this conversation. Nothing "
            "changed. Use ::<style> @project or plain ::<style> instead."
        )
    return (
        "StyleLatch: no project detected here, so a project latch could never "
        "be matched back. Nothing changed.\n"
        "  StyleLatch looks upward from the working directory for .git, .hg, "
        ".jj, .svn, or .stylelatch/styles."
    )


def _shadow_warning(scope: str) -> str:
    """Warn when a latch was set that something more specific already beats."""
    winner = _style.effective()
    if winner is None or winner[0] == scope:
        return ""
    name = winner[1].get("profile", "?")
    return (
        f"\n\nNote: a {winner[0]} latch ({name}) is more specific and still "
        f"wins here, so the {scope} one will not be felt until you clear it "
        f"with ::off @{winner[0]}."
    )


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------


def _handle_off(rest: str, bare: bool) -> str:
    scope, _, bad = split_scope(rest)
    if bad:
        return _scope_problem(bad) + _only_this(bare)

    if scope:
        problem = _unaddressable(scope)
        if problem:
            return problem + _only_this(bare)
        if not _style.clear_latch(scope):
            return (
                f"StyleLatch: nothing was latched {SCOPE_PHRASE[scope]}. Nothing changed."
                + _only_this(bare)
            )
        _style.sync(force=True)
        winner = _style.effective()
        tail = (
            f" The {winner[0]} latch ({winner[1].get('profile')}) applies now."
            if winner
            else " Default output behaviour from here on."
        )
        return f"StyleLatch: cleared the {scope} latch." + tail + _only_this(bare)

    cleared = _style.clear_all_latches()
    detail = f" Cleared: {', '.join(cleared)}." if cleared else ""
    return "StyleLatch: off. Default output behaviour from here on." + detail + _only_this(bare)


def apply(token: str, rest: str, payload: dict[str, Any]) -> str:
    """Run a directive and return the text to inject. Never raises."""
    bare = not rest

    if token in CATALOG_WORDS:
        return catalog_text() + _only_this(bare)

    if token in STATUS_WORDS:
        return _diagnostics.status(payload) + _only_this(bare)

    if token in OFF_WORDS:
        return _handle_off(rest, bare)

    if token in TEST_WORDS:
        return _handle_test(rest, payload)

    # A trailing "!" means this turn only: apply the rules now, latch nothing.
    # "Answer this one in plain English" is a common thing to want, and it
    # should not cost you the style you actually work in.
    one_shot = token.endswith("!")
    token = token.rstrip("!")

    scope, task, bad = split_scope(rest)
    if bad:
        return _scope_problem(bad) + _only_this(bare)
    scope = scope or "global"
    if not one_shot:
        problem = _unaddressable(scope)
        if problem:
            return problem + _only_this(bare)

    parts = [part for part in token.split("+") if part]
    try:
        # Compose before writing anything: an unknown style must change nothing.
        result = _style.compose(parts[0], parts[1:])
    except (KeyError, IndexError):
        hint = suggest(parts[0] if parts else token)
        head = f"StyleLatch: no style called '{token}'. Nothing changed."
        if hint:
            head += " " + hint
        return head + "\n\n" + catalog_text() + _only_this(bare)

    if one_shot:
        if not task:
            return (
                f"StyleLatch: '{token}!' means 'this message only', but this "
                "message carried no task, so there is nothing to apply it to. "
                "Nothing changed. Write the request after it, or drop the '!' "
                "to latch it." + _only_this(True)
            )
        latched = _style.load_state()
        back = (
            f" The {latched.get('label')} latch is untouched and comes back next message."
            if latched.get("enabled")
            else ""
        )
        return (
            f"StyleLatch: {result['label']} ({result['profile']}) for this one "
            f"message only.{back}\n\n{result['document']}\n"
            "Apply the rules above to this message and this message alone. "
            "Nothing was latched, so do not report a style change."
        )

    _style.set_latch(scope, parts[0], parts[1:])
    _style.sync(force=True)

    winner = _style.effective()
    if winner is not None and winner[0] != scope:
        # The latch was stored, but something more specific still decides what
        # the model sees. Saying so beats letting the user wonder why nothing
        # changed -- and the style already in force needs no re-injection.
        return (
            f"StyleLatch: latched {result['label']} ({result['profile']}) "
            f"{SCOPE_PHRASE[scope]}." + _shadow_warning(scope) + _only_this(not task)
        )

    summary = f"StyleLatch: latched {result['label']} ({result['profile']})"
    if result["modifiers"]:
        summary += " + " + ", ".join(result["modifiers"])
    if scope != "global":
        summary += f", {SCOPE_PHRASE[scope]}"

    if not task:
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
