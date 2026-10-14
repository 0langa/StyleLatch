"""The user's own styles live in ~/.stylelatch, never in a plugin data directory.

Claude Code deletes a plugin's data directory when the plugin is uninstalled.
Up to 0.3.1 the user style directory sat inside it under a plugin install, so
an uninstall took every personal style with it.
"""

from __future__ import annotations

import importlib
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from _support import StyleLatchTestCase, _diagnostics, _style

STYLE = '---\nid: "{id}"\nname: {name}\nnudge: {name} nudge.\n---\n\n{body}\n'


class PluginInstallTestCase(StyleLatchTestCase):
    """A host-installed plugin: a plugin data directory and no STYLELATCH_HOME."""

    def setUp(self) -> None:
        super().setUp()
        self._dirs = tempfile.TemporaryDirectory()
        base = Path(self._dirs.name).resolve()
        self.home = base / "home"
        self.data = base / "plugin-data" / "stylelatch-marketplace"
        self.home.mkdir()
        self.data.mkdir(parents=True)
        os.environ.pop("STYLELATCH_HOME")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.home)
        os.environ["CLAUDE_PLUGIN_DATA"] = str(self.data)
        self.old_styles = self.data / "stylelatch" / "styles"
        self.user_styles = self.home / ".stylelatch" / "styles"
        self.new_process()

    def tearDown(self) -> None:
        super().tearDown()
        self._dirs.cleanup()

    def new_process(self) -> None:
        """What the next hook run sees: a fresh import, nothing remembered."""
        importlib.reload(_style)

    def write(self, root: Path, kind: str, id: str, name: str, body: str) -> Path:
        path = root / kind / f"{id}-{name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(STYLE.format(id=id, name=name, body=body), encoding="utf-8")
        return path


class TestUserHome(PluginInstallTestCase):
    def test_user_styles_are_read_from_the_home_directory(self) -> None:
        roots = dict(_style.style_roots())
        self.assertEqual(roots["user"], self.user_styles)
        self.assertEqual(_style.user_styles_dir(), self.user_styles)

    def test_runtime_state_stays_in_the_plugin_data_directory(self) -> None:
        self.assertEqual(_style.state_dir(), self.data / "stylelatch")

    def test_stylelatch_home_still_wins(self) -> None:
        custom = self.home / "elsewhere"
        os.environ["STYLELATCH_HOME"] = str(custom)
        self.assertEqual(_style.user_styles_dir(), custom.resolve() / "styles")

    def test_a_new_style_survives_an_uninstall(self) -> None:
        self.write(self.user_styles, "PROFILES", "50", "mine", "Mine.")
        shutil.rmtree(self.data)  # what Claude Code does on uninstall
        self.new_process()
        self.assertEqual(_style.profiles()["mine"]["source"], "user")

    def test_the_canary_is_planted_in_the_user_directory(self) -> None:
        self.assertEqual(_diagnostics.canary_path(), self.user_styles / "PROFILES" / "99-canary.md")


class TestMove(PluginInstallTestCase):
    def test_styles_in_plugin_data_are_copied_home(self) -> None:
        profile = self.write(self.old_styles, "PROFILES", "50", "mine", "Mine.")
        modifier = self.write(self.old_styles, "MODIFIERS", "60", "loud", "Loud.")
        (self.old_styles / "notes.txt").write_text("not a style\n", encoding="utf-8")

        entry = _style.profiles()["mine"]

        self.assertEqual(entry["source"], "user")
        self.assertEqual(entry["path"], self.user_styles / "PROFILES" / "50-mine.md")
        self.assertEqual(_style.modifiers()["loud"]["source"], "user")
        for old in (profile, modifier, self.old_styles / "notes.txt"):
            new = self.user_styles / old.relative_to(self.old_styles)
            self.assertEqual(new.read_bytes(), old.read_bytes())
            self.assertTrue(old.is_file(), "the old copy is left where it was")

        shutil.rmtree(self.data)
        self.new_process()
        self.assertEqual(_style.profiles()["mine"]["body"], "Mine.")

    def test_an_existing_different_file_is_kept_and_the_old_one_set_aside(self) -> None:
        self.write(self.user_styles, "PROFILES", "50", "mine", "Edited at home.")
        self.write(self.old_styles, "PROFILES", "50", "mine", "From plugin data.")

        self.assertEqual(_style.profiles()["mine"]["body"], "Edited at home.")
        aside = self.home / ".stylelatch" / _style.KEPT_ASIDE_DIRNAME / "PROFILES" / "50-mine.md"
        self.assertIn("From plugin data.", aside.read_text(encoding="utf-8"))
        report = _diagnostics.self_test({})
        self.assertIn("kept aside", report)
        self.assertIn(str(aside), report)

    def test_an_identical_file_is_not_duplicated(self) -> None:
        self.write(self.user_styles, "PROFILES", "50", "mine", "Same.")
        self.write(self.old_styles, "PROFILES", "50", "mine", "Same.")
        _style.style_roots()
        self.assertFalse((self.home / ".stylelatch" / _style.KEPT_ASIDE_DIRNAME).exists())

    def test_running_again_changes_nothing(self) -> None:
        self.write(self.old_styles, "PROFILES", "50", "mine", "Mine.")
        _style.style_roots()
        # The user edits the copy at home, then deletes a style they no longer want.
        home_copy = self.user_styles / "PROFILES" / "50-mine.md"
        home_copy.write_text(STYLE.format(id="50", name="mine", body="Better."), encoding="utf-8")
        self.write(self.old_styles, "MODIFIERS", "60", "loud", "Loud.")
        self.new_process()
        _style.style_roots()
        (self.user_styles / "MODIFIERS" / "60-loud.md").unlink()

        for _ in range(2):
            self.new_process()
            _style.style_roots()

        self.assertIn("Better.", home_copy.read_text(encoding="utf-8"))
        self.assertFalse((self.user_styles / "MODIFIERS" / "60-loud.md").exists())
        self.assertFalse((self.home / ".stylelatch" / _style.KEPT_ASIDE_DIRNAME).exists())

    def test_a_style_edited_in_plugin_data_later_is_copied_again(self) -> None:
        old = self.write(self.old_styles, "PROFILES", "50", "mine", "First.")
        _style.style_roots()
        old.write_text(STYLE.format(id="50", name="mine", body="Second."), encoding="utf-8")
        self.new_process()
        _style.style_roots()
        # The home copy still holds First., so Second. cannot replace it.
        home_copy = self.user_styles / "PROFILES" / "50-mine.md"
        aside = self.home / ".stylelatch" / _style.KEPT_ASIDE_DIRNAME / "PROFILES" / "50-mine.md"
        self.assertIn("First.", home_copy.read_text(encoding="utf-8"))
        self.assertIn("Second.", aside.read_text(encoding="utf-8"))

    def test_a_failed_copy_never_breaks_a_hook(self) -> None:
        self.write(self.old_styles, "PROFILES", "50", "mine", "Mine.")
        # A file where the user directory has to be: nothing can be created in it.
        (self.home / ".stylelatch").write_text("in the way\n", encoding="utf-8")
        self.assertIn("eli5", _style.profiles())

    def test_latching_a_moved_style_from_chat(self) -> None:
        self.write(self.old_styles, "PROFILES", "50", "mine", "Write the way I like it.")
        text = self.context("::mine")
        self.assertIn("latched 50 (mine)", text)
        self.assertIn("Write the way I like it.", text)
        self.assertTrue((self.user_styles / "PROFILES" / "50-mine.md").is_file())
        # The latch itself is runtime state and stays in the plugin data directory.
        self.assertTrue((self.data / "stylelatch" / _style.STATE_FILE).is_file())


if __name__ == "__main__":
    unittest.main()
