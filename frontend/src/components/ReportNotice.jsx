import { useState } from "react";

const REPORT_PATH_PATTERN =
  /(?:[A-Za-z]:[\\/]|\/|(?:\.{1,2}|reports)[\\/])[^\r\n"'<>]*?\.docx\b/i;
const SAFE_REPORT_FILENAME_PATTERN =
  /^[A-Za-z0-9][A-Za-z0-9._-]*\.docx$/i;

/** Find a report file path in an answer without interpreting other text. */
function findReportPath(answer) {
  if (typeof answer !== "string") {
    return null;
  }
  return answer.match(REPORT_PATH_PATTERN)?.[0]?.trim() || null;
}

/** Prefer the structured filename and retain answer parsing for older fixtures. */
function getReportPath(answer, reportFilename) {
  if (
    typeof reportFilename === "string" &&
    SAFE_REPORT_FILENAME_PATTERN.test(reportFilename)
  ) {
    return `reports/${reportFilename}`;
  }
  return findReportPath(answer);
}

/** Show only the report filename and a button to copy its path. */
export function ReportNotice({ answer, reportFilename }) {
  const [copyStatus, setCopyStatus] = useState("idle");
  const reportPath = getReportPath(answer, reportFilename);
  if (!reportPath) {
    return null;
  }

  const pathParts = reportPath.split(/[\\/]/);
  const filename = pathParts[pathParts.length - 1];

  /** Copy the detected path and report clipboard failures on the button. */
  async function handleCopyPath() {
    try {
      if (!navigator.clipboard?.writeText) {
        setCopyStatus("failed");
        return;
      }
      await navigator.clipboard.writeText(reportPath);
      setCopyStatus("copied");
    } catch {
      setCopyStatus("failed");
    }
  }

  const buttonLabel =
    copyStatus === "copied"
      ? "Copied"
      : copyStatus === "failed"
        ? "Copy failed"
        : "Copy path";

  return (
    <section className="report-notice" aria-label="Generated report">
      <span className="report-notice__filename">{filename}</span>
      <button
        className="button button--secondary"
        onClick={handleCopyPath}
        type="button"
        aria-live="polite"
      >
        {buttonLabel}
      </button>
    </section>
  );
}
