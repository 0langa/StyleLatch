"""Scoped latches: session, then project, then global — and the migration."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from _support import StyleLatchTestCase, _diagnostics, _directives, _style


class ScopeTestCase(StyleLatchTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._project = tempfile.TemporaryDirectory()
        self._saved_project = os.environ.get("STYLELATCH_PROJECT")
        self.project = Path(self._project.name).resolve()
        os.environ["STYLELATCH_PROJECT"] = str(self.project)
        _style.set_session_hint("session-under-test")

    def tearDown(self) -> None:
        _style.set_session_hint(None)
        if self._saved_project is None:
            os.environ.pop("STYLELATCH_PROJECT", None)
        else:
            os.environ["STYLELATCH_PROJECT"] = self._saved_project
        self._project.cleanup()
        super().tearDown()

    def context(self, prompt: str, **payload) -> str:
        payload.setdefault("session_id", "session-under-test")
        return super().context(prompt, **payload)


class TestMigration(StyleLatchTestCase):
    def _write_v1(self, **fields) -> None:
        _style.state_dir().mkdir(parents=True, exist_ok=True)
        _style.state_path().write_text(json.dumps(fields, indent=2), encoding="utf-8")

    def test_a_v1_latch_becomes_the_global_latch(self) -> None:
        self._write_v1(
            enabled=True, label="01+02", profile="eli5", modifiers=["no-preamble"], nudge="x"
        )
        state = _style.load_scoped()
        self.assertEqual(state["version"], _style.STATE_VERSION)
        latch = state["latches"]["global"]["*"]
        self.assertEqual(latch["profile"], "eli5")
        self.assertEqual(latch["modifiers"], ["no-preamble"])

    def test_a_disabled_v1_state_migrates_to_nothing_latched(self) -> None:
        self._write_v1(enabled=False, label="01", profile="eli5", modifiers=[])
        self.assertEqual(_style.load_scoped()["latches"]["global"], {})

    def test_migration_keeps_debug_and_restore(self) -> None:
        self._write_v1(
            enabled=True,
            profile="terse",
            modifiers=[],
            debug={"turns_left": 5},
            restore={"profile": "eli5"},
        )
        state = _style.load_scoped()
        self.assertEqual(state["debug"], {"turns_left": 5})
        self.assertEqual(state["restore"], {"profile": "eli5"})

    def test_an_empty_state_migrates_to_an_empty_shape(self) -> None:
        state = _style.load_scoped()
        self.assertEqual(state["version"], _style.STATE_VERSION)
        self.assertEqual(list(state["latches"]), list(_style.SCOPES))

    def test_a_corrupt_state_migrates_to_an_empty_shape(self) -> None:
        _style.state_dir().mkdir(parents=True, exist_ok=True)
        _style.state_path().write_text("{not json", encoding="utf-8")
        self.assertEqual(_style.load_scoped()["latches"]["global"], {})

    def test_migration_is_idempotent(self) -> None:
        self._write_v1(enabled=True, profile="terse", modifiers=[])
        once = _style.load_scoped()
        _style.save_state_raw(once)
        twice = _style.load_scoped()
        self.assertEqual(once["latches"], twice["latches"])

    def test_a_v1_state_still_injects_after_migration(self) -> None:
        self._write_v1(enabled=True, label="02", profile="terse", modifiers=[], nudge="old")
        text = self.context("carry on")
        # Recomposed from the migrated latch, not replayed from the old nudge.
        self.assertIn("OUTPUT STYLE 02 ACTIVE", text)
        self.assertNotIn("old", text)


class TestPrecedence(ScopeTestCase):
    def test_global_is_the_default_scope(self) -> None:
        self.context("::terse")
        self.assertEqual(_style.effective()[0], "global")

    def test_project_beats_global(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        scope, latch = _style.effective()
        self.assertEqual((scope, latch["profile"]), ("project", "eli5"))

    def test_session_beats_project(self) -> None:
        self.context("::terse @project")
        self.context("::eli5 @session")
        scope, latch = _style.effective()
        self.assertEqual((scope, latch["profile"]), ("session", "eli5"))

    def test_a_project_latch_does_not_follow_you_elsewhere(self) -> None:
        self.context("::terse @project")
        with tempfile.TemporaryDirectory() as elsewhere:
            os.environ["STYLELATCH_PROJECT"] = str(Path(elsewhere).resolve())
            self.assertIsNone(_style.effective())

    def test_a_session_latch_does_not_follow_you_to_a_new_session(self) -> None:
        self.context("::terse @session")
        _style.set_session_hint("a-different-session")
        self.assertIsNone(_style.effective())

    def test_a_global_latch_survives_both(self) -> None:
        self.context("::terse")
        _style.set_session_hint("a-different-session")
        with tempfile.TemporaryDirectory() as elsewhere:
            os.environ["STYLELATCH_PROJECT"] = str(Path(elsewhere).resolve())
            self.assertEqual(_style.effective()[0], "global")


class TestScopeSyntax(ScopeTestCase):
    def test_every_alias_lands_on_its_scope(self) -> None:
        for word, scope in _directives.SCOPE_WORDS.items():
            self.assertEqual(_directives.split_scope(f"@{word}"), (scope, "", ""), word)

    def test_a_scope_can_be_followed_by_a_task(self) -> None:
        self.assertEqual(
            _directives.split_scope("@project fix the parser"), ("project", "fix the parser", "")
        )

    def test_no_scope_leaves_the_task_alone(self) -> None:
        self.assertEqual(_directives.split_scope("fix the parser"), ("", "fix the parser", ""))

    def test_an_unknown_scope_is_reported(self) -> None:
        self.assertEqual(_directives.split_scope("@nowhere")[2], "nowhere")

    def test_an_unknown_scope_changes_nothing(self) -> None:
        self.context("::terse")
        text = self.context("::eli5 @nowhere")
        self.assertIn("no scope called '@nowhere'", text)
        self.assertEqual(_style.effective()[1]["profile"], "terse")

    def test_the_reply_names_the_scope(self) -> None:
        self.assertIn("for this project", self.context("::terse @project"))
        self.assertIn("for this session only", self.context("::eli5 @session"))

    def test_a_scoped_latch_still_carries_the_task(self) -> None:
        text = self.context("::terse @project fix the parser")
        self.assertIn("the user's actual request", text)

    def test_setting_a_scope_that_cannot_win_says_so(self) -> None:
        self.context("::eli5 @session")
        text = self.context("::terse @project")
        self.assertIn("a session latch (eli5) is more specific", text)
        self.assertIn("::off @session", text)


class TestUnaddressableScopes(ScopeTestCase):
    """A latch stored under a key nothing can look up is worse than a refusal.

    The user would be told "latched" and then watch nothing happen, with the
    state file quietly accumulating entries under an empty key.
    """

    def test_a_project_latch_without_a_project_is_refused(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        with tempfile.TemporaryDirectory() as bare:
            text = self.context("::terse @project", cwd=bare)
            self.assertIn("no project detected here", text)
            self.assertIn(".stylelatch/styles", text)
        self.assertIsNone(_style.effective())

    def test_a_session_latch_without_a_session_id_is_refused(self) -> None:
        text = self.hook("user_prompt_submit.py", {"prompt": "::terse @session"})
        injected = text["hookSpecificOutput"]["additionalContext"]
        self.assertIn("did not send a session id", injected)
        _style.set_session_hint("")
        self.assertIsNone(_style.effective())

    def test_clearing_an_unaddressable_scope_is_refused_too(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        with tempfile.TemporaryDirectory() as bare:
            self.assertIn("no project detected", self.context("::off @project", cwd=bare))

    def test_nothing_is_written_under_an_empty_key(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        with tempfile.TemporaryDirectory() as bare:
            self.context("::terse @project", cwd=bare)
        self.assertEqual(_style.load_scoped()["latches"]["project"], {})


class TestTurningOff(ScopeTestCase):
    def test_off_clears_every_scope(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        self.context("::silent-run @session")
        text = self.context("::off")
        self.assertIn("Cleared:", text)
        self.assertIsNone(_style.effective())
        self.assertFalse(_style.is_active())

    def test_off_with_a_scope_clears_only_that_one(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        text = self.context("::off @project")
        self.assertIn("cleared the project latch", text)
        self.assertIn("The global latch (terse) applies now", text)
        self.assertEqual(_style.effective()[0], "global")

    def test_off_with_a_scope_that_had_nothing(self) -> None:
        self.assertIn("nothing was latched for this project", self.context("::off @project"))

    def test_off_with_an_unknown_scope_changes_nothing(self) -> None:
        self.context("::terse")
        self.assertIn("no scope called", self.context("::off @nowhere"))
        self.assertIsNotNone(_style.effective())

    def test_off_when_nothing_was_on(self) -> None:
        self.assertIn("Default output behaviour", self.context("::off"))


class TestSync(ScopeTestCase):
    def test_the_mirror_follows_the_winning_scope(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        state = _style.load_state()
        self.assertEqual(state["scope"], "project")
        self.assertEqual(state["profile"], "eli5")
        self.assertIn("Simplified Technical English", _style.read_active())

    def test_a_session_start_recomposes_from_the_latch(self) -> None:
        self.context("::terse")
        result = self.hook(
            "session_start.py", {"session_id": "session-under-test", "source": "startup"}
        )
        self.assertIn("Maximum signal", result["hookSpecificOutput"]["additionalContext"])

    def test_a_latch_pointing_at_a_deleted_style_injects_nothing(self) -> None:
        state = _style.load_scoped()
        state["latches"]["global"]["*"] = {"profile": "gone-zz", "modifiers": [], "at": time.time()}
        _style.save_state_raw(state)
        self.assertIsNone(_style.sync(force=True))
        self.assertFalse(_style.is_active())
        self.assertEqual(self.hook("user_prompt_submit.py", {"prompt": "hi"}), {"continue": True})

    def test_old_latches_are_pruned(self) -> None:
        state = _style.load_scoped()
        for index in range(_style.MAX_REMEMBERED + 10):
            state["latches"]["project"][f"/p/{index}"] = {
                "profile": "terse",
                "modifiers": [],
                "at": float(index),
            }
        _style.save_state_raw(state)
        _style.set_latch("project", "eli5", [])
        kept = _style.load_scoped()["latches"]["project"]
        self.assertLessEqual(len(kept), _style.MAX_REMEMBERED)
        # The newest survives; the oldest is what goes.
        self.assertIn(_style.scope_key("project"), kept)
        self.assertNotIn("/p/0", kept)


class TestOneShot(ScopeTestCase):
    """ "::terse! do this" applies the rules now and latches nothing.

    "Answer this one in plain English" is a common thing to want, and it
    should not cost you the style you actually work in.
    """

    def test_the_parser_keeps_the_bang(self) -> None:
        self.assertEqual(_directives.parse("::terse!"), ("terse!", ""))
        self.assertEqual(_directives.parse("::terse! fix it"), ("terse!", "fix it"))
        self.assertEqual(_directives.parse("::eli5+no-preamble!"), ("eli5+no-preamble!", ""))

    def test_it_injects_the_rules(self) -> None:
        text = self.context("::terse! explain this regex")
        self.assertIn("for this one message only", text)
        self.assertIn("Maximum signal", text)
        self.assertIn("this message alone", text)

    def test_it_latches_nothing(self) -> None:
        self.context("::terse! explain this regex")
        self.assertIsNone(_style.effective())
        self.assertFalse(_style.is_active())

    def test_it_leaves_an_existing_latch_alone(self) -> None:
        self.context("::eli5")
        self.context("::silent-run! run the build")
        scope, latch = _style.effective()
        self.assertEqual((scope, latch["profile"]), ("global", "eli5"))

    def test_it_says_what_comes_back(self) -> None:
        self.context("::eli5")
        text = self.context("::silent-run! run the build")
        self.assertIn("The 01 latch is untouched", text)

    def test_it_stacks_modifiers(self) -> None:
        text = self.context("::eli5+no-preamble! explain this")
        self.assertIn("Start with the substance", text)

    def test_a_bare_one_shot_has_nothing_to_apply_to(self) -> None:
        text = self.context("::terse!")
        self.assertIn("carried no task", text)
        self.assertIsNone(_style.effective())

    def test_an_unknown_one_shot_changes_nothing(self) -> None:
        self.context("::eli5")
        text = self.context("::nonsense-zz! do it")
        self.assertIn("Nothing changed", text)
        self.assertEqual(_style.effective()[1]["profile"], "eli5")

    def test_it_does_not_need_an_addressable_scope(self) -> None:
        # A one-shot stores nothing, so "no project here" is irrelevant to it.
        os.environ.pop("STYLELATCH_PROJECT")
        with tempfile.TemporaryDirectory() as bare:
            text = self.context("::terse! do the thing", cwd=bare)
            self.assertIn("for this one message only", text)


class TestHistory(ScopeTestCase):
    def test_it_starts_empty(self) -> None:
        self.assertEqual(_style.history(), [])

    def test_a_latch_is_recorded_most_recent_first(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        past = _style.history()
        self.assertEqual(past[0]["profile"], "eli5")
        self.assertEqual(past[0]["scope"], "project")
        self.assertEqual(past[1]["profile"], "terse")

    def test_clearing_is_recorded_too(self) -> None:
        self.context("::terse")
        self.context("::off")
        self.assertEqual(_style.history()[0]["action"], "clear")

    def test_modifiers_are_remembered(self) -> None:
        self.context("::eli5+no-preamble")
        self.assertEqual(_style.history()[0]["modifiers"], ["no-preamble"])

    def test_a_one_shot_is_not_history(self) -> None:
        # It changed nothing, so it is not part of the record of what changed.
        self.context("::terse! do it")
        self.assertEqual(_style.history(), [])

    def test_it_is_bounded(self) -> None:
        state = _style.load_scoped()
        state["history"] = [
            {"at": float(i), "action": "latch", "scope": "global", "profile": "terse"}
            for i in range(_style.MAX_HISTORY + 20)
        ]
        _style.save_state_raw(state)
        _style.set_latch("global", "eli5", [])
        self.assertEqual(len(_style.load_scoped()["history"]), _style.MAX_HISTORY)
        self.assertEqual(_style.history()[0]["profile"], "eli5")

    def test_it_survives_a_latch_and_a_clear(self) -> None:
        self.context("::terse")
        self.context("::eli5")
        self.context("::off")
        self.assertEqual(len(_style.history()), 3)

    def test_status_shows_it(self) -> None:
        self.context("::terse")
        report = _diagnostics.status({})
        self.assertIn("recently", report)
        self.assertIn("latched terse (global)", report)


class TestStatus(ScopeTestCase):
    def test_it_says_when_nothing_is_latched(self) -> None:
        self.assertIn("nothing is latched", _diagnostics.status({}))

    def test_it_marks_the_winning_scope(self) -> None:
        self.context("::terse")
        self.context("::eli5 @project")
        report = _diagnostics.status({})
        self.assertIn("(project)", report)
        self.assertIn("> project", report)
        self.assertIn("terse", report)

    def test_it_reports_the_cost_of_both_layers(self) -> None:
        self.context("::terse")
        report = _diagnostics.status({})
        self.assertIn("layer 2", report)
        self.assertIn("layer 3", report)
        self.assertIn("tokens", report)

    def test_it_reports_debug_mode(self) -> None:
        self.context("::test on")
        self.assertIn("debug        ON", _diagnostics.status({}))

    def test_it_reports_an_armed_canary(self) -> None:
        _diagnostics.arm_canary()
        self.assertIn("canary       armed", _diagnostics.status({}))

    def test_every_alias_reaches_it(self) -> None:
        for word in _directives.STATUS_WORDS:
            self.assertIn("StyleLatch status", self.context(f"::{word}"), word)

    def test_it_changes_nothing(self) -> None:
        self.context("::terse")
        before = _style.load_state()
        self.context("::status")
        self.assertEqual(_style.load_state()["label"], before["label"])


if __name__ == "__main__":
    unittest.main()
