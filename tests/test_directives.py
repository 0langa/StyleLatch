"""The `::` surface: parsing, dispatch, and the messages users actually read."""

from __future__ import annotations

import unittest

from _support import StyleLatchTestCase, _directives, _style


class TestParsing(StyleLatchTestCase):
    def test_plain_forms(self) -> None:
        self.assertEqual(_directives.parse("::eli5"), ("eli5", ""))
        self.assertEqual(_directives.parse("::eli5+red-balls"), ("eli5+red-balls", ""))
        self.assertEqual(
            _directives.parse("  ::01+04  fix the parser"), ("01+04", "fix the parser")
        )

    def test_forgiving_forms(self) -> None:
        """Somebody half-remembering the syntax should still land on it."""
        for text in (": :terse", ":: terse", " : : terse", "::  terse"):
            self.assertEqual(_directives.parse(text), ("terse", ""), text)

    def test_case_is_ignored(self) -> None:
        self.assertEqual(_directives.parse("::ELI5"), ("eli5", ""))
        self.assertEqual(_directives.parse("::TestLatch"), ("testlatch", ""))

    def test_subcommands_land_in_the_rest(self) -> None:
        self.assertEqual(_directives.parse("::test on"), ("test", "on"))
        self.assertEqual(
            _directives.parse("::test verify SL-DOC-abc"), ("test", "verify SL-DOC-abc")
        )

    def test_punctuation_ends_the_token(self) -> None:
        self.assertEqual(_directives.parse("::terse, please"), ("terse", ", please"))

    def test_does_not_fire_mid_sentence(self) -> None:
        self.assertIsNone(_directives.parse("we could use :: as a prefix"))
        self.assertIsNone(_directives.parse("no directive here"))
        self.assertIsNone(_directives.parse(""))

    def test_does_not_fire_on_a_bare_colon_run(self) -> None:
        self.assertIsNone(_directives.parse("::"))
        self.assertIsNone(_directives.parse(":"))
        self.assertIsNone(_directives.parse(":: "))

    def test_does_not_fire_on_a_single_colon_word(self) -> None:
        self.assertIsNone(_directives.parse(":note this down"))


class TestSwitching(StyleLatchTestCase):
    def test_switch_works_with_nothing_latched_yet(self) -> None:
        # The first ever "::" is typed when no style is active. It must work.
        self.assertFalse(_style.is_active())
        text = self.context("::eli5+red-balls")
        self.assertIn("latched 01+04", text)
        self.assertTrue(_style.is_active())
        self.assertEqual(_style.load_state()["label"], "01+04")

    def test_bare_directive_injects_the_rules_and_asks_for_a_stub_reply(self) -> None:
        text = self.context("::eli5")
        self.assertIn("STRICT ENFORCEMENT", text)
        self.assertIn('"latched: 01"', text)

    def test_directive_with_a_task_keeps_the_task(self) -> None:
        text = self.context("::terse fix the parser")
        self.assertIn("latched 02", text)
        self.assertIn("the user's actual request", text)
        self.assertNotIn('latched: 02" and nothing else', text)

    def test_off_disables(self) -> None:
        self.context("::eli5")
        self.assertTrue(_style.is_active())
        self.context("::off")
        self.assertFalse(_style.is_active())

    def test_every_off_word_works(self) -> None:
        for word in _directives.OFF_WORDS:
            self.context("::eli5")
            self.context(f"::{word}")
            self.assertFalse(_style.is_active(), word)


class TestCatalog(StyleLatchTestCase):
    def test_question_mark_lists_without_changing_anything(self) -> None:
        _style.write_state(_style.compose("01", []))
        text = self.context("::?")
        self.assertIn("red-balls", text)
        self.assertIn("Latched now: 01", text)
        self.assertEqual(_style.load_state()["label"], "01")

    def test_catalog_shows_every_style_once(self) -> None:
        text = _directives.catalog_text()
        for entry in _style.unique(_style.profiles()):
            self.assertEqual(text.count(f" {entry['name']:<16}"), 1, entry["name"])

    def test_catalog_is_reachable_by_every_alias(self) -> None:
        for word in _directives.CATALOG_WORDS:
            self.assertIn("PROFILES", self.context(f"::{word}"), word)


class TestUnknownStyles(StyleLatchTestCase):
    def test_unknown_name_changes_nothing_and_shows_the_catalog(self) -> None:
        _style.write_state(_style.compose("01", []))
        text = self.context("::nonsense-zz")
        self.assertIn("Nothing changed", text)
        self.assertIn("PROFILES", text)
        self.assertEqual(_style.load_state()["label"], "01")

    def test_a_near_miss_gets_a_suggestion(self) -> None:
        self.assertIn("::eli5", _directives.suggest("elif"))
        self.assertIn("::terse", _directives.suggest("terce"))
        self.assertIn("::silent-run", _directives.suggest("silentrun"))

    def test_a_wild_miss_gets_no_suggestion(self) -> None:
        self.assertEqual(_directives.suggest("qqqqqqqq"), "")

    def test_the_suggestion_reaches_the_user(self) -> None:
        self.assertIn("Did you mean ::eli5", self.context("::elif"))

    def test_an_unknown_modifier_does_not_latch_the_profile(self) -> None:
        text = self.context("::eli5+nonsense-zz")
        self.assertIn("Nothing changed", text)
        self.assertFalse(_style.is_active())


class TestQuiet(StyleLatchTestCase):
    def test_no_directive_and_no_style_costs_nothing(self) -> None:
        self.assertEqual(
            self.hook("user_prompt_submit.py", {"prompt": "hello"}), {"continue": True}
        )


if __name__ == "__main__":
    unittest.main()
