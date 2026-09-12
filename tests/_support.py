"""Shared fixtures.

Every test points STYLELATCH_HOME at a temporary directory, so a test run
never reads or writes the real state at ~/.stylelatch. Every subprocess also
gets STYLELATCH_ROOT, so a hook run out of process resolves the same styles
the in-process tests do.
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
HOOKS = ROOT / "hooks" / "scripts"
sys.path.insert(0, str(HOOKS))

import _adherence  # noqa: E402  -- must follow the sys.path line above
import _diagnostics  # noqa: E402
import _directives  # noqa: E402
import _style  # noqa: E402

__all__ = [
    "HOOKS",
    "ROOT",
    "StyleLatchTestCase",
    "_adherence",
    "_diagnostics",
    "_directives",
    "_style",
]


class StyleLatchTestCase(unittest.TestCase):
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

    # -- running a hook the way a provider would ---------------------------

    def hook(self, script: str, payload: dict | None = None) -> dict:
        """Run a hook entrypoint in its own process and return its JSON."""
        env = dict(os.environ)
        env["STYLELATCH_ROOT"] = str(ROOT)
        env["PYTHONIOENCODING"] = "utf-8"
        proc = subprocess.run(
            [sys.executable, "-S", str(HOOKS / script)],
            input=json.dumps(payload or {}),
            capture_output=True,
            text=True,
            errors="replace",
            env=env,
            timeout=60,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)

    def context(self, prompt: str, **payload) -> str:
        """The text a prompt hook injects, or "" when it stays quiet."""
        payload["prompt"] = prompt
        result = self.hook("user_prompt_submit.py", payload)
        return result.get("hookSpecificOutput", {}).get("additionalContext", "")
