"""Where styles come from: project, then user, then the built-ins."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from _support import StyleLatchTestCase, _directives, _style

STYLE = """---
id: "{id}"
name: {name}
nudge: {nudge}
---

{body}
"""


def write_style(root: Path, kind: str, *, id: str, name: str, nudge: str, body: str) -> Path:
    directory = root / kind
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{id}-{name}.md"
    path.write_text(STYLE.format(id=id, name=name, nudge=nudge, body=body), encoding="utf-8")
    return path


class SourceTestCase(StyleLatchTestCase):
    """Adds an isolated project directory on top of the isolated state dir."""

    def setUp(self) -> None:
        super().setUp()
        self._project = tempfile.TemporaryDirectory()
        self._saved_project = os.environ.get("STYLELATCH_PROJECT")
        # Resolve it. A Windows runner hands out 8.3 short paths such as
        # C:\Users\RUNNER~1\..., and StyleLatch resolves every path it reports,
        # so an unresolved fixture path would never match its own output.
        self.project = Path(self._project.name).resolve()
        os.environ["STYLELATCH_PROJECT"] = str(self.project)
        self.user_styles = _style.state_dir() / "styles"
        self.project_styles = self.project / _style.PROJECT_DIRNAME / "styles"

    def tearDown(self) -> None:
        if self._saved_project is None:
            os.environ.pop("STYLELATCH_PROJECT", None)
        else:
            os.environ["STYLELATCH_PROJECT"] = self._saved_project
        self._project.cleanup()
        super().tearDown()


class TestRoots(SourceTestCase):
    def test_three_roots_in_precedence_order(self) -> None:
        labels = [label for label, _ in _style.style_roots()]
        self.assertEqual(labels, ["project", "user", "built-in"])

    def test_a_root_is_never_listed_twice(self) -> None:
        # A project that IS the plugin checkout must not list the built-ins
        # once as "project" and once as "built-in".
        os.environ["STYLELATCH_PROJECT"] = str(_style.plugin_root())
        paths = [path for _, path in _style.style_roots()]
        self.assertEqual(len(paths), len(set(paths)))

    def test_project_root_walks_up_to_a_marker(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        (self.project / ".git").mkdir()
        deep = self.project / "src" / "deep" / "nested"
        deep.mkdir(parents=True)
        _style.set_project_hint(str(deep))
        try:
            self.assertEqual(_style.project_root(), self.project.resolve())
        finally:
            _style.set_project_hint(None)

    def test_the_home_directory_is_never_a_project(self) -> None:
        """Regression: ~/.stylelatch is the default state directory.

        With a bare ".stylelatch" as a project marker, the home directory
        became a project the moment anyone wrote a personal style, and every
        session anywhere under it silently inherited those styles.
        """
        os.environ.pop("STYLELATCH_PROJECT")
        _style.set_project_hint(str(Path.home()))
        try:
            self.assertIsNone(_style.project_root())
        finally:
            _style.set_project_hint(None)

    def test_a_project_directory_with_styles_is_a_marker(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        (self.project / _style.PROJECT_DIRNAME / "styles").mkdir(parents=True)
        _style.set_project_hint(str(self.project))
        try:
            self.assertEqual(_style.project_root(), self.project.resolve())
        finally:
            _style.set_project_hint(None)

    def test_project_root_is_none_without_a_marker(self) -> None:
        os.environ.pop("STYLELATCH_PROJECT")
        bare = self.project / "no-markers-anywhere"
        bare.mkdir()
        _style.set_project_hint(str(bare))
        try:
            root = _style.project_root()
        finally:
            _style.set_project_hint(None)
        # A temp directory has no repository above it on any supported OS.
        self.assertIsNone(root)


class TestDiscovery(SourceTestCase):
    def test_a_user_style_is_found(self) -> None:
        write_style(
            self.user_styles,
            "PROFILES",
            id="50",
            name="mine",
            nudge="Mine. Short.",
            body="Write the way I like it.",
        )
        self.assertIn("mine", _style.profiles())
        self.assertEqual(_style.profiles()["mine"]["source"], "user")

    def test_a_project_style_is_found(self) -> None:
        write_style(
            self.project_styles,
            "PROFILES",
            id="60",
            name="house",
            nudge="House voice.",
            body="The voice this repository agreed on.",
        )
        self.assertEqual(_style.profiles()["house"]["source"], "project")

    def test_a_user_modifier_is_found(self) -> None:
        write_style(
            self.user_styles,
            "MODIFIERS",
            id="51",
            name="loud",
            nudge="SHOUT.",
            body="Use capitals.",
        )
        self.assertEqual(_style.modifiers()["loud"]["source"], "user")

    def test_built_ins_still_work_untouched(self) -> None:
        self.assertEqual(_style.profiles()["eli5"]["source"], "built-in")
        self.assertEqual(_style.modifiers()["no-preamble"]["source"], "built-in")

    def test_an_unreadable_style_is_skipped_not_fatal(self) -> None:
        directory = self.user_styles / "PROFILES"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "70-broken.md").write_bytes(b"\xff\xfe\x00 not text at all")
        # The built-ins must still resolve.
        self.assertIn("eli5", _style.profiles())


class TestShadowing(SourceTestCase):
    def _override_eli5(self, root: Path, marker: str) -> None:
        write_style(
            root,
            "PROFILES",
            id="01",
            name="eli5",
            nudge=f"{marker} nudge.",
            body=f"{marker} rules for eli5.",
        )

    def test_user_overrides_a_built_in(self) -> None:
        self._override_eli5(self.user_styles, "USER")
        entry = _style.profiles()["eli5"]
        self.assertEqual(entry["source"], "user")
        self.assertIn("USER rules", _style.compose("eli5", [])["document"])

    def test_project_overrides_user(self) -> None:
        self._override_eli5(self.user_styles, "USER")
        self._override_eli5(self.project_styles, "PROJECT")
        self.assertEqual(_style.profiles()["eli5"]["source"], "project")
        self.assertIn("PROJECT rules", _style.compose("eli5", [])["document"])

    def test_the_id_follows_the_winner(self) -> None:
        self._override_eli5(self.project_styles, "PROJECT")
        self.assertEqual(_style.profiles()["01"]["source"], "project")

    def test_a_shadowed_style_is_reported_not_hidden(self) -> None:
        self._override_eli5(self.user_styles, "USER")
        shadowed = [e for e in _style.collect("PROFILES") if e["shadowed_by"] is not None]
        self.assertEqual(len(shadowed), 1)
        self.assertEqual(shadowed[0]["source"], "built-in")
        self.assertEqual(shadowed[0]["shadowed_by"]["source"], "user")

    def test_nothing_is_shadowed_by_default(self) -> None:
        for kind in ("PROFILES", "MODIFIERS"):
            for entry in _style.collect(kind):
                self.assertIsNone(entry["shadowed_by"], entry["name"])


class TestSurface(SourceTestCase):
    def test_the_catalog_marks_a_non_built_in(self) -> None:
        write_style(
            self.user_styles,
            "PROFILES",
            id="50",
            name="mine",
            nudge="Mine.",
            body="Body.",
        )
        text = _directives.catalog_text()
        self.assertIn("[user] Mine.", text)
        # A built-in stays unmarked, so an override is impossible to miss.
        self.assertNotIn("[built-in]", text)

    def test_the_catalog_names_every_root(self) -> None:
        text = _directives.catalog_text()
        for source, path in _style.style_roots():
            self.assertIn(source, text)
            self.assertIn(str(path), text)

    def test_the_catalog_explains_a_shadow(self) -> None:
        write_style(self.user_styles, "PROFILES", id="01", name="eli5", nudge="Mine.", body="Body.")
        self.assertIn("SHADOWED", _directives.catalog_text())

    def test_latching_a_user_style_from_chat(self) -> None:
        write_style(
            self.user_styles,
            "PROFILES",
            id="50",
            name="mine",
            nudge="Mine. Short sentences.",
            body="Write the way I like it.",
        )
        text = self.context("::mine")
        self.assertIn("latched 50 (mine)", text)
        self.assertIn("Write the way I like it.", text)
        self.assertEqual(_style.load_state()["profile"], "mine")

    def test_the_self_test_lists_the_roots(self) -> None:
        from _support import _diagnostics

        report = _diagnostics.self_test({})
        self.assertIn("styles are read from", report)
        self.assertIn(str(self.project_styles), report)

    def test_the_self_test_reports_a_shadow_without_failing(self) -> None:
        from _support import _diagnostics

        write_style(self.user_styles, "PROFILES", id="01", name="eli5", nudge="Mine.", body="Body.")
        report = _diagnostics.self_test({})
        self.assertIn("is shadowed by the user one", report)
        self.assertIn("all checks pass", report)

    def test_a_user_profile_without_a_nudge_fails_the_check(self) -> None:
        from _support import _diagnostics

        directory = self.user_styles / "PROFILES"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "52-nonudge.md").write_text(
            '---\nid: "52"\nname: nonudge\n---\n\nSome rules.\n', encoding="utf-8"
        )
        report = _diagnostics.self_test({})
        self.assertIn("FAIL", report)
        self.assertIn("'nonudge' has no nudge", report)


if __name__ == "__main__":
    unittest.main()
