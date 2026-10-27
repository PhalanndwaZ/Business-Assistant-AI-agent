"""Tests for the generated Markdown test-run report."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import run_tests


def test_report_lists_pass_skip_and_failure_details(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The report reflects each JUnit outcome and includes failure messages."""
    junit_path = tmp_path / "sample-junit.xml"
    junit_path.write_text(
        """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite tests="3" failures="1" skipped="1">
    <testcase classname="tests.sample" name="passing" file="tests/sample.py"/>
    <testcase classname="tests.sample" name="failing" file="tests/sample.py">
      <failure message="expected value">assert 1 == 2</failure>
    </testcase>
    <testcase classname="tests.sample" name="skipped" file="tests/sample.py">
      <skipped message="requires external service"/>
    </testcase>
  </testsuite>
</testsuites>
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_tests, "REPORT_DIR", tmp_path)

    report_path = run_tests._write_report("sample", junit_path)
    report = report_path.read_text(encoding="utf-8")

    assert "- Total: 3" in report
    assert "- Passed: 1" in report
    assert "- Failed: 1" in report
    assert "- Skipped: 1" in report
    assert "**FAIL** `tests/sample.py::failing`" in report
    assert "assert 1 == 2" in report


def test_failed_pytest_start_does_not_report_stale_junit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A runner failure cannot reuse XML left by an earlier test run."""
    monkeypatch.setattr(run_tests, "REPORT_DIR", tmp_path)
    monkeypatch.setattr(
        run_tests,
        "_arguments",
        lambda: SimpleNamespace(suite="data", verbose=False),
    )
    old_report = tmp_path / "data-junit.xml"
    old_report.write_text("<testsuite tests='1'/>", encoding="utf-8")
    monkeypatch.setattr(
        run_tests.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1),
    )

    result = run_tests.main()

    assert result == 1
    assert not old_report.exists()
    assert not (tmp_path / "data-report.md").exists()
