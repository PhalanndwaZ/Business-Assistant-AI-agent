"""Run deterministic project tests and write a readable, machine-linked report."""

from __future__ import annotations

import argparse
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_DIR = PROJECT_ROOT / "evaluation" / "reports"
SUITE_PATHS = {
    "data": (
        "tests/test_config.py",
        "tests/test_data_loading.py",
        "tests/test_analyses.py",
        "tests/test_data_tool.py",
        "tests/test_evidence_check.py",
    ),
    "rag": (
        "tests/test_rag_ingestion.py",
        "tests/test_retrieval.py",
    ),
    "workflow": (
        "tests/test_graph.py",
        "tests/test_phase5_cli_smoke.py",
    ),
    "all": ("tests",),
}


def _arguments() -> argparse.Namespace:
    """Parse the test suite and verbosity requested by the caller."""
    parser = argparse.ArgumentParser(
        description=(
            "Run offline deterministic tests. No Groq or Mistral API keys "
            "are required."
        )
    )
    parser.add_argument(
        "--suite",
        choices=sorted(SUITE_PATHS),
        default="all",
        help="Test suite to run (default: all).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show each test result while pytest runs.",
    )
    return parser.parse_args()


def _write_report(suite: str, junit_path: Path) -> Path:
    """Convert pytest's JUnit XML into a concise Markdown run report."""
    root = ET.parse(junit_path).getroot()
    test_suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
    cases = [
        testcase
        for test_suite in test_suites
        for testcase in test_suite.findall("testcase")
    ]
    failures = []
    for testcase in cases:
        failure = testcase.find("failure")
        if failure is None:
            failure = testcase.find("error")
        if failure is not None:
            failures.append((testcase, failure))
    skipped = sum(testcase.find("skipped") is not None for testcase in cases)
    passed = len(cases) - len(failures) - skipped

    lines = [
        f"# Test run: {suite}",
        "",
        f"- Total: {len(cases)}",
        f"- Passed: {passed}",
        f"- Failed: {len(failures)}",
        f"- Skipped: {skipped}",
        f"- JUnit details: `{junit_path.name}`",
        "",
        "## Test cases",
        "",
    ]
    for testcase in cases:
        status = (
            "SKIP"
            if testcase.find("skipped") is not None
            else "FAIL"
            if testcase.find("failure") is not None
            or testcase.find("error") is not None
            else "PASS"
        )
        test_name = testcase.get("name", "unnamed test")
        test_file = testcase.get("file", "")
        lines.append(f"- **{status}** `{test_file}::{test_name}`")

    if failures:
        lines.extend(("", "## Failure details", ""))
        for testcase, detail in failures:
            if detail is not None:
                failure_message = detail.get(
                    "message",
                    detail.text or "No failure message.",
                )
                failure_trace = (detail.text or "").strip()
                if failure_trace and failure_trace != failure_message:
                    failure_message = f"{failure_message}\n\n{failure_trace}"
                lines.extend(
                    [
                        f"### `{testcase.get('name', 'unnamed test')}`",
                        "",
                        "```text",
                        failure_message,
                        "```",
                        "",
                    ]
                )
    report_path = REPORT_DIR / f"{suite}-report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path


def main() -> int:
    """Run the selected pytest suite and return pytest's exit code."""
    args = _arguments()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    junit_path = REPORT_DIR / f"{args.suite}-junit.xml"
    pytest_arguments = [
        "-m",
        "pytest",
        "-ra",
        "--junitxml",
        str(junit_path),
        *SUITE_PATHS[args.suite],
    ]
    if args.verbose:
        pytest_arguments.insert(2, "-v")

    if junit_path.exists():
        junit_path.unlink()
    completed = subprocess.run(
        [sys.executable, *pytest_arguments],
        cwd=PROJECT_ROOT,
        check=False,
    )
    if junit_path.exists():
        report_path = _write_report(args.suite, junit_path)
        print(f"\nReadable test report: {report_path}")
        print(f"JUnit XML report: {junit_path}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
