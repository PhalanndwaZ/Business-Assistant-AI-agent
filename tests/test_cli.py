"""Tests for invoking the CLI directly from its application directory."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_DIRECTORY = PROJECT_ROOT / "app"


def test_direct_cli_invocation_from_app_directory() -> None:
    """Running cli.py from app/ resolves the project package and shows help."""
    result = subprocess.run(
        [sys.executable, "cli.py", "--help"],
        cwd=APP_DIRECTORY,
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert "Ask one question about the synthetic business datasets." in result.stdout


def test_cli_stdout_accepts_unicode_answers() -> None:
    """The Windows console encoding must not crash on normal model punctuation."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import app.cli; "
                "exec(\"async def fake_answer(question):\\n"
                " return 'supply\\\\u2011chain'\"); "
                "app.cli._answer = fake_answer; "
                "raise SystemExit(app.cli.main())"
            ),
            "Unicode output test",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "supply\u2011chain"
