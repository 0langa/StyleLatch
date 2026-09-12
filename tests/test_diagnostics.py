"""`::test` -- the self-check, debug mode, the canary, and verification."""

from __future__ import annotations

import json
import time
import unittest

from _support import StyleLatchTestCase, _diagnostics, _style


class TestSelfTest(StyleLatchTestCase):
    def test_a_healthy_tree_passes_everything(self) -> None:
        report = _diagnostics.self_test({})
        self.assertIn("all checks pass", report)
        self.assertNotIn("FAIL", report)

    def test_report_names_where_state_and_styles_live(self) -> None:
        report = _diagnostics.self_test({"session_id": "abc"})
        self.assertIn(str(_style.state_dir()), report)
        self.assertIn(str(_style.plugin_root()), report)
        self.assertIn("abc", report)

    def test_an_unwritable_state_dir_fails_loudly(self) -> None:
        import os

        # Point the state directory below a regular file, so mkdir cannot win.
        blocker = _style.state_dir() / "blocker"
        blocker.parent.mkdir(parents=True, exist_ok=True)
        blocker.write_text("not a directory", encoding="utf-8")
        os.environ["STYLELATCH_HOME"] = str(blocker / "state")

        report = _diagnostics.self_test({})
        self.assertIn("FAIL  state directory is writable", report)
        self.assertIn("not writable", report)
        self.assertIn("check(s) FAILED", report)
        self.assertIn("Most likely causes", report)

    def test_reaching_it_from_chat(self) -> None:
        self.assertIn("StyleLatch self-test", self.context("::test"))

    def test_every_alias_reaches_it(self) -> None:
        from _support import _directives

        for word in _directives.TEST_WORDS:
            self.assertIn("StyleLatch", self.context(f"::{word}"), word)

    def test_a_question_after_test_is_still_the_users_question(self) -> None:
        text = self.context("::test why is my style not applying")
        self.assertIn("StyleLatch self-test", text)
        self.assertNotIn("no task attached", text)


class TestDebugMode(StyleLatchTestCase):
    def test_off_by_default_and_free(self) -> None:
        self.assertEqual(_diagnostics.debug_info(), {})
        self.assertEqual(_diagnostics.tick_debug({"prompt": "hi"}), "")

    def test_turning_it_on_reports_the_payload(self) -> None:
        text = self.context(
            "::test on",
            session_id="s1",
            cwd="C:/repo",
            transcript_path="C:/t.jsonl",
            hook_event_name="UserPromptSubmit",
        )
        self.assertIn("debug mode ON", text)
        self.assertIn("STYLELATCH DEBUG", text)
        self.assertIn("C:/repo", text)
        self.assertIn("C:/t.jsonl", text)
        self.assertEqual(_diagnostics.debug_info()["turns_left"], _diagnostics.DEBUG_TURNS)

    def test_each_turn_spends_one_of_the_budget(self) -> None:
        self.context("::test on", session_id="s1")
        before = _diagnostics.debug_info()["turns_left"]
        text = self.context("do something", session_id="s1")
        self.assertIn("STYLELATCH DEBUG", text)
        self.assertEqual(_diagnostics.debug_info()["turns_left"], before - 1)

    def test_it_ends_when_the_budget_runs_out(self) -> None:
        self.context("::test on", session_id="s1")
        state = _style.load_state()
        state["debug"]["turns_left"] = 1
        _style.save_state_raw(state)

        self.assertIn("STYLELATCH DEBUG", self.context("one", session_id="s1"))
        text = self.context("two", session_id="s1")
        self.assertIn("ended by itself (turn budget spent)", text)
        self.assertEqual(_diagnostics.debug_info(), {})

    def test_it_ends_when_the_clock_runs_out(self) -> None:
        self.context("::test on", session_id="s1")
        state = _style.load_state()
        state["debug"]["expires_at"] = time.time() - 1
        _style.save_state_raw(state)

        text = self.context("later", session_id="s1")
        self.assertIn("ended by itself (time limit reached)", text)
        self.assertEqual(_diagnostics.debug_info(), {})

    def test_it_ends_when_the_session_changes(self) -> None:
        self.context("::test on", session_id="s1")
        text = self.context("hello", session_id="s2")
        self.assertIn("ended by itself (session changed)", text)
        self.assertEqual(_diagnostics.debug_info(), {})

    def test_a_session_start_retires_a_stale_debug_mode(self) -> None:
        self.context("::test on", session_id="s1")
        result = self.hook("session_start.py", {"session_id": "s2", "source": "startup"})
        text = result["hookSpecificOutput"]["additionalContext"]
        self.assertIn("session changed", text)
        self.assertEqual(_diagnostics.debug_info(), {})

    def test_a_session_start_in_the_same_session_keeps_it(self) -> None:
        self.context("::test on", session_id="s1")
        result = self.hook("session_start.py", {"session_id": "s1", "source": "compact"})
        self.assertIn("STYLELATCH DEBUG", result["hookSpecificOutput"]["additionalContext"])
        self.assertTrue(_diagnostics.debug_info())

    def test_turning_it_off_is_immediate(self) -> None:
        self.context("::test on", session_id="s1")
        text = self.context("::test off", session_id="s1")
        self.assertIn("debug mode OFF", text)
        self.assertNotIn("STYLELATCH DEBUG", text)
        self.assertEqual(_diagnostics.debug_info(), {})

    def test_turning_it_off_when_it_was_never_on(self) -> None:
        self.assertIn("was not on", self.context("::test off"))

    def test_it_survives_a_style_switch(self) -> None:
        self.context("::test on", session_id="s1")
        self.context("::terse", session_id="s1")
        self.assertTrue(_diagnostics.debug_info())

    def test_the_block_carries_the_injection_cost(self) -> None:
        self.context("::eli5")
        self.context("::test on", session_id="s1")
        text = self.context("anything", session_id="s1")
        self.assertIn("layer 2", text)
        self.assertIn("layer 3", text)
        self.assertIn("tokens", text)


class TestCanary(StyleLatchTestCase):
    def test_arming_latches_two_distinct_tokens(self) -> None:
        report = _diagnostics.arm_canary()
        document = _style.read_active()
        nudge = _style.nudge_text()

        doc_token = next(w for w in report.split() if w.startswith("SL-DOC-"))
        nudge_token = next(w for w in report.split() if w.startswith("SL-NDG-"))
        self.assertNotEqual(doc_token, nudge_token)

        # Each token proves exactly one layer, so neither may leak into the other.
        self.assertIn(doc_token, document)
        self.assertNotIn(doc_token, nudge)
        self.assertIn(nudge_token, nudge)
        self.assertNotIn(nudge_token, document)

    def test_tokens_are_fresh_every_time(self) -> None:
        first = _diagnostics.arm_canary()
        second = _diagnostics.arm_canary()
        self.assertNotEqual(first, second)

    def test_it_remembers_what_to_restore(self) -> None:
        self.context("::eli5+no-preamble")
        report = _diagnostics.arm_canary()
        self.assertEqual(_style.load_state()["restore"]["label"], "01+02")
        self.assertIn("go back with ::01+02", report)

    def test_arming_twice_does_not_forget_the_original(self) -> None:
        self.context("::terse")
        _diagnostics.arm_canary()
        _diagnostics.arm_canary()
        self.assertEqual(_style.load_state()["restore"]["label"], "02")

    def test_it_writes_no_files_into_the_plugin(self) -> None:
        before = sorted(p.name for p in _style.profiles_dir().glob("*.md"))
        _diagnostics.arm_canary()
        after = sorted(p.name for p in _style.profiles_dir().glob("*.md"))
        self.assertEqual(before, after)


class TestVerify(StyleLatchTestCase):
    def _transcript(self, *records: dict) -> str:
        path = _style.state_dir() / "transcript.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        return str(path)

    def test_it_finds_both_markers(self) -> None:
        path = self._transcript(
            {"role": "developer", "content": "STRICT ENFORCEMENT: obey every rule"},
            {"role": "developer", "content": "OUTPUT STYLE 01 ACTIVE"},
        )
        report = _diagnostics.verify_injection({"transcript_path": path})
        self.assertIn("FOUND    SessionStart document", report)
        self.assertIn("FOUND    UserPromptSubmit nudge", report)
        self.assertIn("reached the API", report)

    def test_a_missing_marker_is_reported_with_next_steps(self) -> None:
        path = self._transcript({"role": "developer", "content": "OUTPUT STYLE 01 ACTIVE"})
        report = _diagnostics.verify_injection({"transcript_path": path})
        self.assertIn("ABSENT   SessionStart document", report)
        self.assertIn("stale installed copy", report)

    def test_it_searches_nested_structures(self) -> None:
        path = self._transcript(
            {"payload": {"content": [{"text": "STRICT ENFORCEMENT"}]}},
            {"payload": {"content": [{"text": "OUTPUT STYLE 02 ACTIVE"}]}},
        )
        self.assertIn("reached the API", _diagnostics.verify_injection({"transcript_path": path}))

    def test_a_custom_needle_is_checked_too(self) -> None:
        path = self._transcript({"content": "STRICT ENFORCEMENT and SL-DOC-deadbeef here"})
        report = _diagnostics.verify_injection({"transcript_path": path}, "SL-DOC-deadbeef")
        self.assertIn("custom: SL-DOC-deadbeef", report)

    def test_unreadable_lines_are_skipped_not_fatal(self) -> None:
        path = _style.state_dir() / "broken.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"content": "STRICT ENFORCEMENT"}\nnot json\n{"content": "OUTPUT STYLE 01"}\n',
            encoding="utf-8",
        )
        report = _diagnostics.verify_injection({"transcript_path": str(path)})
        self.assertIn("reached the API", report)

    def test_a_missing_transcript_says_so(self) -> None:
        report = _diagnostics.verify_injection({"transcript_path": "/no/such/file.jsonl"})
        self.assertIn("no session transcript found", report)


if __name__ == "__main__":
    unittest.main()
