"""The plugin has to load before anything else about it can matter.

Four manifests describe the same plugin to three audiences — the portable
spec, Claude Code, Codex, and a marketplace listing. Nothing keeps them in
agreement except this file.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from _support import ROOT, StyleLatchTestCase, _style

MANIFESTS = (
    "plugin.json",
    ".claude-plugin/plugin.json",
    ".codex-plugin/plugin.json",
)
PORTABLE_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
# From the portable spec: lowercase, no leading or trailing separator, and no
# doubled "--" or "..".
NAME_PATTERN = re.compile(r"^(?!.*(?:--|\.\.))[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$")


def load(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


class TestManifests(unittest.TestCase):
    def test_every_manifest_parses(self) -> None:
        for relative in (*MANIFESTS, ".claude-plugin/marketplace.json"):
            self.assertIsInstance(load(relative), dict, relative)

    def test_they_agree_on_name_and_version(self) -> None:
        first = load(MANIFESTS[0])
        for relative in MANIFESTS[1:]:
            other = load(relative)
            self.assertEqual(other["name"], first["name"], relative)
            self.assertEqual(other["version"], first["version"], relative)

    def test_the_marketplace_entry_agrees_too(self) -> None:
        plugin = load(".claude-plugin/plugin.json")
        market = load(".claude-plugin/marketplace.json")
        entry = next(p for p in market["plugins"] if p["name"] == plugin["name"])
        self.assertEqual(entry["version"], plugin["version"])
        self.assertEqual(entry["source"], "./")

    def test_the_name_is_valid_under_the_portable_spec(self) -> None:
        for relative in MANIFESTS:
            name = load(relative)["name"]
            self.assertRegex(name, NAME_PATTERN, relative)

    def test_the_portable_manifest_declares_its_schema(self) -> None:
        self.assertEqual(load("plugin.json")["$schema"], PORTABLE_SCHEMA)

    def test_the_portable_manifest_uses_only_spec_fields(self) -> None:
        allowed = {
            "$schema",
            "name",
            "version",
            "description",
            "author",
            "homepage",
            "repository",
            "license",
            "keywords",
            "extensions",
        }
        self.assertLessEqual(set(load("plugin.json")), allowed)

    def test_no_manifest_declares_a_hooks_path(self) -> None:
        # hooks/hooks.json is auto-discovered by both providers. Declaring it
        # as well double-registers on Claude Code and fails the plugin load
        # with "Duplicate hooks file".
        for relative in MANIFESTS:
            self.assertNotIn("hooks", load(relative), relative)

    def test_every_manifest_names_an_author_and_a_licence(self) -> None:
        for relative in MANIFESTS:
            manifest = load(relative)
            self.assertIn("author", manifest, relative)
            self.assertEqual(manifest.get("license"), "MIT", relative)


def _posix_shell() -> str | None:
    """A POSIX sh to run hook commands through, as the hosts do, or None."""
    if sys.platform != "win32":
        return shutil.which("sh")
    # Claude Code uses Git Bash on Windows. Find it through git itself, so a
    # WSL bash.exe on PATH is never picked up by mistake.
    git = shutil.which("git")
    if not git:
        return None
    # list(): slicing Path.parents needs Python 3.10.
    for ancestor in list(Path(git).resolve().parents)[:3]:
        candidate = ancestor / "bin" / "sh.exe"
        if candidate.is_file():
            return str(candidate)
    return None


class TestHookCommands(unittest.TestCase):
    """Every hook's `command` has to find a Python on every host that runs it.

    Claude Code runs `command` through a POSIX shell everywhere -- Git Bash on
    Windows -- and does not read `commandWindows`, which only Codex honours. On
    Windows `python3` is usually the Microsoft Store alias, which prints
    "Python was not found" and exits non-zero, so a bare `python3` meant no
    StyleLatch hook ever ran under Claude Code on Windows.

    Each case puts fake interpreters first on PATH and runs the real command
    strings from hooks/hooks.json through sh.
    """

    STUB = "#!/bin/sh\necho 'Python was not found' >&2\nexit 49\n"

    def setUp(self) -> None:
        self.shell = _posix_shell()
        if self.shell is None:
            self.skipTest("no POSIX shell available")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.bin = Path(self._tmp.name) / "bin"
        self.bin.mkdir()
        self.home = Path(self._tmp.name) / "home"
        self.real = Path(sys.executable).as_posix()

    def fake(self, name: str, body: str) -> None:
        path = self.bin / name
        # Bytes, not text: a CRLF shebang line would not run under sh.
        path.write_bytes(body.encode("utf-8"))
        path.chmod(0o755)

    def real_python(self, name: str, *, drop_flag: str = "") -> None:
        shift = f'[ "$1" = {drop_flag} ] && shift\n' if drop_flag else ""
        self.fake(name, f'#!/bin/sh\n{shift}exec "{self.real}" "$@"\n')

    def run_every_hook(self, windows: bool) -> None:
        hooks = load("hooks/hooks.json")["hooks"]
        env = {
            key: value
            for key, value in os.environ.items()
            if key not in ("OS", "PLUGIN_ROOT", "STYLELATCH_ROOT")
        }
        env.update(
            {
                "PATH": str(self.bin),
                "CLAUDE_PLUGIN_ROOT": str(ROOT),
                "STYLELATCH_HOME": str(self.home),
                "PYTHONIOENCODING": "utf-8",
            }
        )
        if windows:
            env["OS"] = "Windows_NT"
        for event in ("SessionStart", "UserPromptSubmit", "Stop"):
            command = hooks[event][0]["hooks"][0]["command"]
            proc = subprocess.run(
                [self.shell, "-c", command],
                input=json.dumps({"prompt": "::status", "session_id": "s1"}),
                capture_output=True,
                text=True,
                env=env,
                timeout=60,
            )
            self.assertEqual(proc.returncode, 0, f"{event}: {proc.stderr}")
            self.assertTrue(json.loads(proc.stdout)["continue"], event)

    def test_a_posix_host_runs_python3(self) -> None:
        self.real_python("python3")
        self.run_every_hook(windows=False)

    def test_windows_prefers_the_launcher_over_the_store_alias(self) -> None:
        self.fake("python3", self.STUB)
        self.fake("python", self.STUB)
        self.real_python("py", drop_flag="-3")
        self.run_every_hook(windows=True)

    def test_windows_without_the_launcher_falls_back_to_python(self) -> None:
        self.fake("python3", self.STUB)
        self.real_python("python")
        self.run_every_hook(windows=True)


class TestReleaseConsistency(unittest.TestCase):
    """A tag that disagrees with a manifest installs the wrong code silently."""

    def test_the_changelog_has_a_section_for_the_current_version(self) -> None:
        version = load("plugin.json")["version"]
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn(f"## [{version}]", changelog)

    def test_the_release_checker_passes_for_the_current_version(self) -> None:
        version = load("plugin.json")["version"]
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_release.py"), f"v{version}"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_the_release_checker_rejects_a_mismatched_tag(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "check_release.py"), "v99.99.99"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("not consistent", proc.stdout)

    def test_the_changelog_section_extractor_finds_the_current_version(self) -> None:
        version = load("plugin.json")["version"]
        proc = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "changelog_section.py"), version],
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("No changelog section", proc.stdout)
        self.assertTrue(proc.stdout.strip())


class TestSkill(unittest.TestCase):
    """Both providers auto-discover skills/<name>/SKILL.md."""

    PATH = ROOT / "skills" / "stylelatch" / "SKILL.md"

    def setUp(self) -> None:
        self.meta, self.body = _style.parse_frontmatter(self.PATH.read_text(encoding="utf-8"))

    def test_it_lives_where_both_providers_look(self) -> None:
        self.assertTrue(self.PATH.is_file())

    def test_it_declares_a_name_and_description(self) -> None:
        self.assertEqual(self.meta.get("name"), "stylelatch")
        self.assertTrue(self.meta.get("description"))

    def test_the_description_says_when_to_use_it(self) -> None:
        # A description that only says what a skill *is* never triggers.
        description = self.meta["description"].lower()
        self.assertIn("use when", description)

    def test_it_documents_every_directive_word_group(self) -> None:
        from _support import _directives

        for word in ("::off", "::test", "::status", "::?"):
            self.assertIn(word, self.body, word)
        for scope in _directives.SCOPE_PHRASE:
            self.assertIn(f"@{scope}", self.body, scope)

    def test_it_states_the_safety_boundary(self) -> None:
        self.assertIn("never governs", self.body)


class TestCommand(unittest.TestCase):
    PATH = ROOT / "commands" / "styles.md"

    def setUp(self) -> None:
        self.meta, self.body = _style.parse_frontmatter(self.PATH.read_text(encoding="utf-8"))

    def test_it_lives_where_claude_code_looks(self) -> None:
        self.assertTrue(self.PATH.is_file())

    def test_it_declares_a_name_and_description(self) -> None:
        self.assertEqual(self.meta.get("name"), "styles")
        self.assertTrue(self.meta.get("description"))

    def test_it_points_at_the_renderer_through_the_plugin_root(self) -> None:
        # A hardcoded path works in a checkout and breaks in an install.
        self.assertIn("${CLAUDE_PLUGIN_ROOT}", self.body)
        self.assertIn("hooks/scripts/_show.py", self.body)


class TestNoNameCollisions(unittest.TestCase):
    """Claude Code lists skills and commands in one inventory.

    Two components sharing an invocation name means one shadows the other in
    the "/" menu -- which is exactly what shipping skills/stylelatch alongside
    commands/stylelatch.md did in v0.2.0.
    """

    def _names(self, folder: str, pattern: str) -> list[str]:
        names = []
        for path in sorted((ROOT / folder).glob(pattern)):
            meta, _ = _style.parse_frontmatter(path.read_text(encoding="utf-8"))
            names.append(meta.get("name") or path.stem)
        return names

    def test_no_command_shares_a_name_with_a_skill(self) -> None:
        skills = self._names("skills", "*/SKILL.md")
        commands = self._names("commands", "*.md")
        self.assertTrue(skills and commands)
        self.assertEqual(set(skills) & set(commands), set())

    def test_names_are_unique_within_each_kind(self) -> None:
        for names in (self._names("skills", "*/SKILL.md"), self._names("commands", "*.md")):
            self.assertEqual(len(names), len(set(names)), names)


class TestRenderer(StyleLatchTestCase):
    """_show.py backs the slash command. It is a renderer, not a CLI."""

    def _run(self) -> str:
        import os

        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-S", str(ROOT / "hooks" / "scripts" / "_show.py")],
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_it_prints_the_catalogue_and_the_status(self) -> None:
        output = self._run()
        self.assertIn("PROFILES (pick one)", output)
        self.assertIn("StyleLatch status", output)

    def test_it_survives_a_cp1252_console(self) -> None:
        # Regression: a modifier with an emoji in it crashed the old CLI.
        import os

        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        env["PYTHONIOENCODING"] = "cp1252"
        proc = subprocess.run(
            [sys.executable, "-S", str(ROOT / "hooks" / "scripts" / "_show.py")],
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_it_takes_no_arguments(self) -> None:
        source = (ROOT / "hooks" / "scripts" / "_show.py").read_text(encoding="utf-8")
        self.assertNotIn("argparse", source)
        self.assertNotIn("sys.argv", source)

    def test_it_changes_no_latch(self) -> None:
        self.context("::terse")
        before = _style.load_state()["label"]
        self._run()
        self.assertEqual(_style.load_state()["label"], before)


if __name__ == "__main__":
    unittest.main()
