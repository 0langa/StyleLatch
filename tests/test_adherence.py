"""Measuring whether the style actually held, and correcting when it did not."""

from __future__ import annotations

import json
import unittest

from _support import StyleLatchTestCase, _adherence, _style


class TestRuleLanguage(StyleLatchTestCase):
    def test_it_parses_every_kind_of_rule(self) -> None:
        rules, problems = _adherence.parse_checks(
            "max_sentence_words=20; forbid=Great question; no_headings"
        )
        self.assertEqual(problems, [])
        self.assertEqual(
            rules, [("max_sentence_words", "20"), ("forbid", "Great question"), ("no_headings", "")]
        )

    def test_empty_means_no_rules(self) -> None:
        self.assertEqual(_adherence.parse_checks(""), ([], []))
        self.assertEqual(_adherence.parse_checks("  ;  ; "), ([], []))

    def test_an_unknown_rule_is_reported_not_fatal(self) -> None:
        rules, problems = _adherence.parse_checks("be_nicer=yes; forbid=x")
        self.assertEqual(rules, [("forbid", "x")])
        self.assertIn("unknown check 'be_nicer'", problems)

    def test_a_counting_rule_needs_a_positive_number(self) -> None:
        for bad in ("max_sentence_words=lots", "max_reply_lines=0", "max_reply_chars=-3"):
            rules, problems = _adherence.parse_checks(bad)
            self.assertEqual(rules, [], bad)
            self.assertTrue(problems, bad)

    def test_a_text_rule_needs_something_to_look_for(self) -> None:
        rules, problems = _adherence.parse_checks("forbid=")
        self.assertEqual(rules, [])
        self.assertTrue(problems)

    def test_every_built_in_declaration_is_valid(self) -> None:
        for kind in ("PROFILES", "MODIFIERS"):
            for entry in _style.collect(kind):
                _rules, problems = _adherence.parse_checks(entry["checks"])
                self.assertEqual(problems, [], f"{entry['name']}: {problems}")

    def test_checks_accumulate_across_a_composition(self) -> None:
        alone, _ = _adherence.parse_checks(_style.compose("02", [])["checks"])
        stacked, _ = _adherence.parse_checks(_style.compose("02", ["show-evidence"])["checks"])
        self.assertGreater(len(stacked), len(alone))


class TestEvaluation(StyleLatchTestCase):
    def rules(self, text: str):
        rules, problems = _adherence.parse_checks(text)
        self.assertEqual(problems, [])
        return rules

    def test_a_clean_reply_breaks_nothing(self) -> None:
        rules = self.rules("max_sentence_words=10; forbid=sorry; no_bullets")
        self.assertEqual(_adherence.evaluate("Done. Tests pass.", rules), [])

    def test_a_long_sentence_is_caught_and_quoted(self) -> None:
        rules = self.rules("max_sentence_words=5")
        broken = _adherence.evaluate("One two three four five six seven eight.", rules)
        self.assertEqual(len(broken), 1)
        self.assertIn("8-word sentence (max 5)", broken[0])
        self.assertIn("One two three", broken[0])

    def test_code_is_not_prose(self) -> None:
        """A rule about sentence length is not talking about a shell command."""
        rules = self.rules("max_sentence_words=5")
        reply = "Done.\n\n```\nfind . -name '*.py' -exec grep -l TODO {} + | sort | head -20\n```\n"
        self.assertEqual(_adherence.evaluate(reply, rules), [])

    def test_inline_code_is_not_prose_either(self) -> None:
        rules = self.rules("forbid=should work")
        self.assertEqual(_adherence.evaluate("See `should work` in the docs.", rules), [])

    def test_a_bullet_is_not_a_sentence(self) -> None:
        rules = self.rules("max_sentence_words=4")
        self.assertEqual(_adherence.evaluate("- one two three four five six", rules), [])

    def test_forbid_is_case_insensitive(self) -> None:
        rules = self.rules("forbid=Great question")
        self.assertTrue(_adherence.evaluate("GREAT QUESTION, here goes.", rules))

    def test_forbid_opening_only_looks_at_the_opening(self) -> None:
        rules = self.rules("forbid_opening=hope that helps")
        late = "x" * 300 + " hope that helps"
        self.assertEqual(_adherence.evaluate(late, rules), [])
        self.assertTrue(_adherence.evaluate("Hope that helps. Here it is.", rules))

    def test_require_catches_an_omission(self) -> None:
        rules = self.rules("require=verified")
        self.assertTrue(_adherence.evaluate("It works.", rules))
        self.assertEqual(_adherence.evaluate("Verified: it works.", rules), [])

    def test_line_character_and_paragraph_limits(self) -> None:
        self.assertTrue(_adherence.evaluate("a\nb\nc", self.rules("max_reply_lines=2")))
        self.assertTrue(_adherence.evaluate("abcdef", self.rules("max_reply_chars=3")))
        self.assertTrue(_adherence.evaluate("a\n\nb\n\nc", self.rules("max_paragraphs=2")))

    def test_headings_and_bullets(self) -> None:
        self.assertTrue(_adherence.evaluate("# Title\ntext", self.rules("no_headings")))
        self.assertTrue(_adherence.evaluate("- one\n- two", self.rules("no_bullets")))
        self.assertEqual(_adherence.evaluate("plain text", self.rules("no_headings")), [])

    def test_several_breaches_are_all_reported(self) -> None:
        rules = self.rules("forbid=sorry; no_bullets; max_reply_lines=1")
        broken = _adherence.evaluate("Sorry!\n- a\n- b", rules)
        self.assertEqual(len(broken), 3)


class TestTranscript(StyleLatchTestCase):
    def write(self, *records: dict) -> str:
        path = _style.state_dir() / "transcript.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "\n".join(json.dumps(record) for record in records) + "\n", encoding="utf-8"
        )
        return str(path)

    def test_it_reads_the_claude_code_shape(self) -> None:
        path = self.write(
            {"type": "user", "message": {"role": "user", "content": "hi"}},
            {
                "type": "assistant",
                "message": {
                    "role": "assistant",
                    "content": [{"type": "text", "text": "the reply"}],
                },
            },
        )
        self.assertEqual(_adherence.last_reply(path), "the reply")

    def test_it_takes_the_last_assistant_message_not_the_last_line(self) -> None:
        path = self.write(
            {"role": "assistant", "content": "older"},
            {"role": "assistant", "content": "newer"},
            {"role": "user", "content": "a question after it"},
        )
        self.assertEqual(_adherence.last_reply(path), "newer")

    def test_it_reads_a_nested_payload_shape(self) -> None:
        path = self.write({"payload": {"role": "assistant", "content": "from a payload"}})
        self.assertEqual(_adherence.last_reply(path), "from a payload")

    def test_it_ignores_user_messages(self) -> None:
        path = self.write({"role": "user", "content": "only a user message"})
        self.assertEqual(_adherence.last_reply(path), "")

    def test_unparseable_lines_are_skipped(self) -> None:
        path = _style.state_dir() / "broken.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            'not json\n{"role": "assistant", "content": "still found"}\nalso not json\n',
            encoding="utf-8",
        )
        self.assertEqual(_adherence.last_reply(str(path)), "still found")

    def test_a_missing_file_is_empty_not_an_error(self) -> None:
        self.assertEqual(_adherence.last_reply("/no/such/file.jsonl"), "")
        self.assertEqual(_adherence.last_reply(""), "")


class TestTheLoop(StyleLatchTestCase):
    """The Stop hook records; the next prompt hook corrects."""

    def transcript(self, reply: str) -> str:
        path = _style.state_dir() / "t.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"type": "assistant", "message": {"role": "assistant", "content": reply}})
            + "\n",
            encoding="utf-8",
        )
        return str(path)

    def stop(self, reply: str, session_id: str = "s1") -> dict:
        return self.hook(
            "stop.py", {"session_id": session_id, "transcript_path": self.transcript(reply)}
        )

    def test_the_stop_hook_injects_nothing(self) -> None:
        self.context("::terse", session_id="s1")
        self.assertEqual(self.stop("Hope that helps."), {"continue": True})

    def test_a_breach_is_recorded(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Done. Hope that helps, let me know if you need anything else.")
        recorded = _adherence.recorded()
        self.assertEqual(len(recorded), 1)
        self.assertTrue(recorded[0]["broken"])

    def test_a_clean_reply_is_recorded_as_clean(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Done.")
        self.assertEqual(_adherence.recorded()[0]["broken"], [])

    def test_the_next_turn_carries_the_correction(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Done. Hope that helps, let me know if you need anything else.")
        text = self.context("carry on", session_id="s1")
        self.assertIn("STYLE BREACH last reply", text)
        self.assertIn("hope that helps", text.lower())

    def test_a_correction_is_delivered_once(self) -> None:
        # Otherwise a host without a Stop hook would nag forever about one reply.
        self.context("::terse", session_id="s1")
        self.stop("Done. Hope that helps.")
        self.assertIn("STYLE BREACH", self.context("one", session_id="s1"))
        self.assertNotIn("STYLE BREACH", self.context("two", session_id="s1"))

    def test_a_clean_reply_produces_no_correction(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Done.")
        self.assertNotIn("STYLE BREACH", self.context("carry on", session_id="s1"))

    def test_a_breach_under_another_style_is_not_this_style_s_problem(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Done. Hope that helps.")
        self.context("::eli5", session_id="s1")
        self.assertNotIn("STYLE BREACH", self.context("carry on", session_id="s1"))

    def test_nothing_is_measured_when_no_style_is_latched(self) -> None:
        self.stop("Hope that helps.")
        self.assertEqual(_adherence.recorded(), [])

    def test_nothing_is_measured_when_the_style_declares_no_checks(self) -> None:
        self.context("::deep-technical", session_id="s1")
        self.stop("Hope that helps, and let me know if you need anything else.")
        self.assertEqual(_adherence.recorded(), [])

    def test_an_unreadable_transcript_records_nothing(self) -> None:
        # Recording a clean turn here would be a lie; a broken one worse.
        self.context("::terse", session_id="s1")
        self.hook("stop.py", {"session_id": "s1", "transcript_path": "/no/such/file.jsonl"})
        self.assertEqual(_adherence.recorded(), [])

    def test_the_record_is_bounded(self) -> None:
        self.context("::terse", session_id="s1")
        for index in range(_adherence.MAX_RECORDED + 5):
            self.stop(f"Reply {index}. Hope that helps.")
        self.assertEqual(len(_adherence.recorded()), _adherence.MAX_RECORDED)

    def test_status_reports_adherence(self) -> None:
        from _support import _diagnostics

        self.context("::terse", session_id="s1")
        self.stop("Done.")
        self.stop("Done. Hope that helps.")
        report = _diagnostics.status({})
        self.assertIn("checks", report)
        self.assertIn("adherence", report)
        self.assertIn("1/2", report)

    def test_status_reports_a_bad_declaration(self) -> None:
        from _support import _diagnostics

        self.context("::terse", session_id="s1")
        state = _style.load_scoped()
        state["checks"] = "be_nicer=yes"
        _style.save_state_raw(state)
        self.assertIn("unknown check 'be_nicer'", _diagnostics.status({}))

    def test_the_correction_stays_inside_its_budget(self) -> None:
        self.context("::terse", session_id="s1")
        self.stop("Hope that helps. " * 40 + "let me know if you need anything else.")
        text = self.context("carry on", session_id="s1")
        breach = next(line for line in text.splitlines() if "STYLE BREACH" in line)
        self.assertLessEqual(len(breach), _adherence.MAX_CORRECTION_CHARS)


class TestSelfTest(StyleLatchTestCase):
    def test_a_broken_check_declaration_fails_the_style_check(self) -> None:
        from _support import _diagnostics

        directory = _style.state_dir() / "styles" / "PROFILES"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "60-bad.md").write_text(
            '---\nid: "60"\nname: badcheck\nnudge: x\nchecks: be_nicer=yes\n---\n\nBody.\n',
            encoding="utf-8",
        )
        report = _diagnostics.self_test({})
        self.assertIn("FAIL", report)
        self.assertIn("'badcheck' checks: unknown check 'be_nicer'", report)

    def test_the_built_ins_still_pass(self) -> None:
        from _support import _diagnostics

        self.assertIn("all checks pass", _diagnostics.self_test({}))


if __name__ == "__main__":
    unittest.main()
