"""Stdlib-only tests. Run: python -m unittest discover -s tests

Every test points STYLELATCH_HOME at a temp dir, so the real state at
~/.stylelatch is never read or written.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "hooks" / "scripts"))

import _style  # noqa: E402


class StyleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self._saved = os.environ.get("STYLELATCH_HOME")
        os.environ["STYLELATCH_HOME"] = self._tmp.name
        importlib.reload(_style)

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop("STYLELATCH_HOME", None)
        else:
            os.environ["STYLELATCH_HOME"] = self._saved
        self._tmp.cleanup()


class TestCatalog(StyleTestCase):
    def test_profiles_are_found_by_id_and_name(self) -> None:
        available = _style.profiles()
        self.assertIn("01", available)
        self.assertIn("eli5", available)
        self.assertIs(available["01"], available["eli5"])

    def test_every_profile_has_a_nudge(self) -> None:
        for entry in _style.unique(_style.profiles()):
            self.assertTrue(entry["nudge"], f"{entry['name']} has no nudge")

    def test_ids_are_unique(self) -> None:
        for catalog in (_style.profiles(), _style.modifiers()):
            entries = _style.unique(catalog)
            ids = [entry["id"] for entry in entries]
            self.assertEqual(len(ids), len(set(ids)))


class TestCompose(StyleTestCase):
    def test_compose_inlines_the_real_rules(self) -> None:
        result = _style.compose("01", [])
        # The whole point: no id left for the agent to resolve.
        self.assertIn("Simplified Technical English", result["document"])
        self.assertIn("STRICT ENFORCEMENT", result["document"])
        self.assertEqual(result["label"], "01")

    def test_modifiers_stack_and_label(self) -> None:
        result = _style.compose("eli5", ["02", "03"])
        self.assertEqual(result["label"], "01+02+03")
        self.assertIn("No opener, no closer.", result["nudge"])
        self.assertIn("Start with the substance", result["document"])
        self.assertIn("Never claim something works", result["document"])

    def test_duplicate_modifier_is_applied_once(self) -> None:
        result = _style.compose("01", ["02", "no-preamble"])
        self.assertEqual(result["modifiers"], ["no-preamble"])

    def test_unknown_keys_raise(self) -> None:
        with self.assertRaises(KeyError):
            _style.compose("no-such-profile-zz", [])
        with self.assertRaises(KeyError):
            _style.compose("01", ["no-such-modifier-zz"])

    def test_nudge_stays_small(self) -> None:
        result = _style.compose("01", ["01", "02", "03"])
        self.assertLessEqual(len(result["nudge"]), _style.MAX_NUDGE_CHARS)


class TestState(StyleTestCase):
    def test_inactive_by_default(self) -> None:
        self.assertFalse(_style.is_active())
        self.assertEqual(_style.load_state(), {})

    def test_write_then_read_back(self) -> None:
        _style.write_state(_style.compose("02", ["01"]))
        self.assertTrue(_style.is_active())
        self.assertIn("Maximum signal", _style.read_active())
        self.assertIn("02+01", _style.nudge_text())

    def test_off_keeps_the_file_but_deactivates(self) -> None:
        _style.write_state(_style.compose("01", []))
        _style.disable()
        self.assertFalse(_style.is_active())
        self.assertTrue(_style.active_path().is_file())

    def test_corrupt_state_is_treated_as_no_style(self) -> None:
        _style.state_dir().mkdir(parents=True, exist_ok=True)
        _style.state_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(_style.load_state(), {})
        self.assertFalse(_style.is_active())


class TestHooks(StyleTestCase):
    def _run(self, script: str) -> dict:
        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-S", str(ROOT / "hooks" / "scripts" / script)],
            input="{}",
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def test_hooks_are_silent_when_no_style_is_set(self) -> None:
        for script in ("session_start.py", "user_prompt_submit.py"):
            payload = self._run(script)
            self.assertEqual(payload, {"continue": True}, script)

    def test_session_start_injects_the_full_document(self) -> None:
        _style.write_state(_style.compose("01", ["02"]))
        payload = self._run("session_start.py")
        specific = payload["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        self.assertIn("STRICT ENFORCEMENT", specific["additionalContext"])
        self.assertIn("Start with the substance", specific["additionalContext"])

    def test_prompt_hook_injects_only_the_small_nudge(self) -> None:
        _style.write_state(_style.compose("01", ["02"]))
        payload = self._run("user_prompt_submit.py")
        specific = payload["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        text = specific["additionalContext"]
        self.assertIn("OUTPUT STYLE 01+02 ACTIVE", text)
        # Layer 3 must stay cheap: it is never the whole contract.
        self.assertNotIn("STRICT ENFORCEMENT", text)
        self.assertLess(len(text), 400)


class TestNonAsciiStyles(StyleTestCase):
    """Regression: a style may contain any character, including emoji.

    Found by 04-red-balls.md, which puts an emoji between every word. The
    hooks were fine (json.dumps escapes to ASCII) but the CLI crashed with
    UnicodeEncodeError on a cp1252 Windows console.
    """

    def test_emoji_modifier_is_discovered(self) -> None:
        self.assertIn("red-balls", _style.modifiers())

    def test_emoji_survives_compose(self) -> None:
        result = _style.compose("01", ["red-balls"])
        self.assertIn("\U0001f3c0", result["nudge"])
        self.assertIn("\U0001f3c0", result["document"])

    def test_hook_output_is_ascii_safe(self) -> None:
        _style.write_state(_style.compose("01", ["red-balls"]))
        payload = json.dumps(_style.additional_context("UserPromptSubmit", _style.nudge_text()))
        payload.encode("ascii")  # json.dumps escapes non-ASCII; must not raise

    def test_cli_does_not_crash_printing_emoji(self) -> None:
        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        env["PYTHONIOENCODING"] = "cp1252"  # force the failing console encoding
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts" / "style.py"),
                "set",
                "01",
                "--with",
                "red-balls",
            ],
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)


class TestDirectives(StyleTestCase):
    """The in-chat switch: "::eli5+red-balls" typed straight into the chat."""

    def _hook(self, prompt: str) -> dict:
        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        proc = subprocess.run(
            [sys.executable, "-S", str(ROOT / "hooks" / "scripts" / "user_prompt_submit.py")],
            input=json.dumps({"prompt": prompt}),
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=30,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def _context(self, prompt: str) -> str:
        return self._hook(prompt)["hookSpecificOutput"]["additionalContext"]

    def test_parses_bare_and_trailing_forms(self) -> None:
        self.assertEqual(_style.parse_directive("::eli5+red-balls"), ("eli5+red-balls", ""))
        self.assertEqual(
            _style.parse_directive("  ::01+04  fix the parser"), ("01+04", "fix the parser")
        )

    def test_does_not_fire_mid_sentence(self) -> None:
        self.assertIsNone(_style.parse_directive("we could use :: as a prefix"))
        self.assertIsNone(_style.parse_directive("no directive here"))

    def test_switch_works_with_nothing_latched_yet(self) -> None:
        # The first ever "::" is typed when no style is active. It must work.
        self.assertFalse(_style.is_active())
        text = self._context("::eli5+red-balls")
        self.assertIn("latched 01+04", text)
        self.assertTrue(_style.is_active())
        self.assertEqual(_style.load_state()["label"], "01+04")

    def test_bare_directive_injects_full_rules_and_asks_for_a_stub_reply(self) -> None:
        text = self._context("::eli5")
        self.assertIn("STRICT ENFORCEMENT", text)
        self.assertIn('"latched: 01"', text)

    def test_directive_with_a_task_keeps_the_task(self) -> None:
        text = self._context("::terse fix the parser")
        self.assertIn("latched 02", text)
        self.assertIn("the user's actual request", text)
        self.assertNotIn('latched: 02" and nothing else', text)

    def test_off_disables(self) -> None:
        self._context("::eli5")
        self.assertTrue(_style.is_active())
        self._context("::off")
        self.assertFalse(_style.is_active())

    def test_question_mark_lists_without_changing_anything(self) -> None:
        _style.write_state(_style.compose("01", []))
        text = self._context("::?")
        self.assertIn("red-balls", text)
        self.assertIn("Latched now: 01", text)
        self.assertEqual(_style.load_state()["label"], "01")

    def test_unknown_name_changes_nothing_and_shows_the_catalog(self) -> None:
        _style.write_state(_style.compose("01", []))
        text = self._context("::nonsense+bogus")
        self.assertIn("Nothing changed", text)
        self.assertIn("PROFILES", text)
        self.assertEqual(_style.load_state()["label"], "01")

    def test_debug_reports_payload_keys(self) -> None:
        text = self._context("::debug")
        self.assertIn("payload keys: prompt", text)
        self.assertIn("prompt text found: yes", text)

    def test_no_directive_and_no_style_costs_nothing(self) -> None:
        self.assertEqual(self._hook("just a normal message"), {"continue": True})


if __name__ == "__main__":
    unittest.main()
