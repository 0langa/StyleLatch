"""The model layer: style files, composition, state, and the two hooks.

Run: python -m unittest discover -s tests
"""

from __future__ import annotations

import json
import unittest

from _support import ROOT, StyleLatchTestCase, _style


class TestCatalog(StyleLatchTestCase):
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
            ids = [entry["id"] for entry in _style.unique(catalog)]
            self.assertEqual(len(ids), len(set(ids)))


class TestCompose(StyleLatchTestCase):
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

    def test_every_built_in_document_fits_the_budget(self) -> None:
        for entry in _style.unique(_style.profiles()):
            result = _style.compose(entry["name"], [])
            self.assertLessEqual(
                len(result["document"]),
                _style.MAX_ACTIVE_CHARS,
                f"{entry['name']} composes over budget",
            )
            self.assertNotIn(
                "…\n",
                result["document"][-3:],
                f"{entry['name']} was truncated by the budget cap",
            )


class TestState(StyleLatchTestCase):
    def test_inactive_by_default(self) -> None:
        self.assertFalse(_style.is_active())
        self.assertEqual(_style.load_state(), {})

    def test_write_then_read_back(self) -> None:
        _style.latch("02", ["01"])
        self.assertTrue(_style.is_active())
        self.assertIn("Maximum signal", _style.read_active())
        self.assertIn("02+01", _style.nudge_text())

    def test_off_keeps_the_file_but_deactivates(self) -> None:
        _style.latch("01", [])
        _style.clear_all_latches()
        self.assertFalse(_style.is_active())
        self.assertTrue(_style.active_path().is_file())

    def test_corrupt_state_is_treated_as_no_style(self) -> None:
        _style.state_dir().mkdir(parents=True, exist_ok=True)
        _style.state_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(_style.load_state(), {})
        self.assertFalse(_style.is_active())

    def test_switching_a_style_preserves_carried_keys(self) -> None:
        # Debug mode has to survive a "::terse" typed in the middle of it.
        _style.latch("01", [])
        state = _style.load_state()
        state["debug"] = {"turns_left": 7}
        state["restore"] = {"label": "03"}
        _style.save_state_raw(state)

        _style.latch("02", [])
        after = _style.load_state()
        self.assertEqual(after["label"], "02")
        self.assertEqual(after["debug"], {"turns_left": 7})
        self.assertEqual(after["restore"], {"label": "03"})

    def test_disable_preserves_carried_keys(self) -> None:
        _style.latch("01", [])
        state = _style.load_state()
        state["debug"] = {"turns_left": 3}
        _style.save_state_raw(state)

        _style.clear_all_latches()
        after = _style.load_state()
        self.assertFalse(after["enabled"])
        self.assertEqual(after["debug"], {"turns_left": 3})


class TestHooks(StyleLatchTestCase):
    def test_hooks_are_silent_when_nothing_is_set(self) -> None:
        for script in ("session_start.py", "user_prompt_submit.py"):
            self.assertEqual(self.hook(script), {"continue": True}, script)

    def test_session_start_injects_the_full_document(self) -> None:
        _style.latch("01", ["02"])
        specific = self.hook("session_start.py")["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        self.assertIn("STRICT ENFORCEMENT", specific["additionalContext"])
        self.assertIn("Start with the substance", specific["additionalContext"])

    def test_prompt_hook_injects_only_the_small_nudge(self) -> None:
        _style.latch("01", ["02"])
        specific = self.hook("user_prompt_submit.py")["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "UserPromptSubmit")
        text = specific["additionalContext"]
        self.assertIn("OUTPUT STYLE 01+02 ACTIVE", text)
        # Layer 3 must stay cheap: it is never the whole contract.
        self.assertNotIn("STRICT ENFORCEMENT", text)
        self.assertLess(len(text), 400)

    def test_a_hook_survives_junk_on_stdin(self) -> None:
        import os
        import subprocess
        import sys

        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        for script in ("session_start.py", "user_prompt_submit.py"):
            proc = subprocess.run(
                [sys.executable, "-S", str(ROOT / "hooks" / "scripts" / script)],
                input="not json at all {[",
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads(proc.stdout), {"continue": True}, script)


class TestNonAsciiStyles(StyleLatchTestCase):
    """Regression: a style may contain any character, including emoji.

    Found by 04-red-balls.md, which puts an emoji between every word.
    """

    def test_emoji_modifier_is_discovered(self) -> None:
        self.assertIn("red-balls", _style.modifiers())

    def test_emoji_survives_compose(self) -> None:
        result = _style.compose("01", ["red-balls"])
        self.assertIn("\U0001f3c0", result["nudge"])
        self.assertIn("\U0001f3c0", result["document"])

    def test_hook_output_is_ascii_safe(self) -> None:
        _style.latch("01", ["red-balls"])
        payload = json.dumps(_style.additional_context("UserPromptSubmit", _style.nudge_text()))
        payload.encode("ascii")  # json.dumps escapes non-ASCII; must not raise


class TestManifests(StyleLatchTestCase):
    """A plugin that will not load is worse than a plugin that misbehaves."""

    def _load(self, relative: str) -> dict:
        return json.loads((ROOT / relative).read_text(encoding="utf-8"))

    def test_manifests_agree_on_name_and_version(self) -> None:
        claude = self._load(".claude-plugin/plugin.json")
        codex = self._load(".codex-plugin/plugin.json")
        self.assertEqual(claude["name"], codex["name"])
        self.assertEqual(claude["version"], codex["version"])

    def test_marketplace_entry_matches_the_plugin(self) -> None:
        plugin = self._load(".claude-plugin/plugin.json")
        market = self._load(".claude-plugin/marketplace.json")
        entry = next(p for p in market["plugins"] if p["name"] == plugin["name"])
        self.assertEqual(entry["version"], plugin["version"])

    def test_hooks_json_registers_both_layers(self) -> None:
        hooks = self._load("hooks/hooks.json")["hooks"]
        self.assertIn("SessionStart", hooks)
        self.assertIn("UserPromptSubmit", hooks)
        matcher = hooks["SessionStart"][0]["matcher"]
        # fork and clear are easy to miss and are exactly where a style dies.
        for event in ("startup", "resume", "clear", "compact", "fork"):
            self.assertIn(event, matcher)

    def test_manifests_do_not_declare_a_hooks_path(self) -> None:
        # Declaring it alongside the default hooks/hooks.json double-registers
        # on Claude Code and fails plugin load with "Duplicate hooks file".
        for relative in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            self.assertNotIn("hooks", self._load(relative), relative)


if __name__ == "__main__":
    unittest.main()
