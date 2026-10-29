<<<<<<< HEAD
import { API_BASE } from "../config.js";

const REPORT_PATH_PATTERN =
  /(?:[A-Za-z]:[\\/]|\/|(?:\.{1,2}|reports)[\\/])[^\r\n"'<>]*?\.docx\b/i;
const SAFE_REPORT_FILENAME_PATTERN =
  /^[A-Za-z0-9][A-Za-z0-9._-]*\.docx$/i;
const GENERATED_ID_PATTERN = /-[a-f0-9]{32}$/i;

/** Find a report file path in an answer without interpreting other text. */
function findReportPath(answer) {
  if (typeof answer !== "string") {
    return null;
  }
  return answer.match(REPORT_PATH_PATTERN)?.[0]?.trim() || null;
}

/** Prefer the structured filename and retain answer parsing for older fixtures. */
export function getReportFilename(answer, reportFilename) {
  if (
    typeof reportFilename === "string" &&
    SAFE_REPORT_FILENAME_PATTERN.test(reportFilename)
  ) {
    return reportFilename;
  }

  const reportPath = findReportPath(answer);
  if (!reportPath) {
=======
import { useState } from "react";
import {
  downloadReport,
  isSafeReportFilename,
} from "../api/reportsApi.js";

/** Show a structured generated report with an authenticated download action. */
export function ReportNotice({ reportFilename }) {
  const [downloadStatus, setDownloadStatus] = useState("idle");
  const [downloadError, setDownloadError] = useState("");
  if (!isSafeReportFilename(reportFilename)) {
>>>>>>> dev
    return null;
  }
  const filename = reportPath.split(/[\\/]/).at(-1);
  return filename && SAFE_REPORT_FILENAME_PATTERN.test(filename)
    ? filename
    : null;
}

<<<<<<< HEAD
/** Remove the raw report path from prose when the download card displays it. */
export function removeReportPathFromAnswer(answer, reportFilename) {
  if (!getReportFilename(answer, reportFilename)) {
    return answer;
  }

  return answer
    .replace(REPORT_PATH_PATTERN, "")
    .replace(/(?:^|\n)\s*Report file:\s*(?=\n|$)/gi, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/** Create a readable report heading from its generated filename. */
function getReportTitle(filename) {
  const slug = filename
    .replace(/\.docx$/i, "")
    .replace(GENERATED_ID_PATTERN, "");
  const words = slug.split("-");

  for (let repeatLength = Math.floor(words.length / 2); repeatLength >= 3; repeatLength -= 1) {
    const suffixStart = words.length - repeatLength;
    const repeatedSuffix = words.slice(suffixStart).join("-");
    let hasRepeatedTitle = false;
    for (let start = 0; start + repeatLength <= suffixStart; start += 1) {
      if (words.slice(start, start + repeatLength).join("-") === repeatedSuffix) {
        words.splice(suffixStart);
        hasRepeatedTitle = true;
        break;
      }
    }
    if (hasRepeatedTitle) {
      break;
    }
  }

  return words
    .map((word) =>
      word.toLowerCase() === "vs" ? "vs." : word[0].toUpperCase() + word.slice(1),
    )
    .join(" ");
}

/** Render a generated report as a downloadable document card in the chat. */
export function ReportNotice({ answer, reportFilename }) {
  const filename = getReportFilename(answer, reportFilename);
  if (!filename) {
    return null;
  }

  const apiBase = API_BASE.replace(/\/+$/, "");
  const downloadUrl = `${apiBase}/reports/${encodeURIComponent(filename)}`;

  return (
    <section className="report-card" aria-label="Generated report">
      <div className="report-card__icon" aria-hidden="true">
        <svg viewBox="0 0 32 40" focusable="false">
          <path d="M5 1.5h14l8 8V36a2.5 2.5 0 0 1-2.5 2.5h-19A2.5 2.5 0 0 1 3 36V4A2.5 2.5 0 0 1 5.5 1.5Z" />
          <path d="M19 2v8h8M8 19h14M8 24h14M8 29h10" />
        </svg>
        <span>DOCX</span>
      </div>
      <div className="report-card__details">
        <h3>{getReportTitle(filename)}</h3>
        <p>{filename}</p>
        <span>Word document</span>
      </div>
      <a
        className="button button--secondary report-card__download"
        download={filename}
        href={downloadUrl}
      >
        <svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">
          <path d="M10 2.5v9m0 0 3.5-3.5M10 11.5 6.5 8M3.5 13v3.5h13V13" />
        </svg>
        <span>Download</span>
      </a>
=======
  async function handleDownload() {
    setDownloadStatus("downloading");
    setDownloadError("");
    try {
      await downloadReport(reportFilename);
      setDownloadStatus("complete");
    } catch (error) {
      setDownloadStatus("failed");
      setDownloadError(
        error instanceof Error
          ? error.message
          : "The report could not be downloaded.",
      );
    }
  }

  const buttonLabel =
    downloadStatus === "downloading"
      ? "Downloading..."
      : downloadStatus === "complete"
        ? "Download again"
        : "Download report";

  return (
    <section className="report-notice" aria-label="Generated report">
      <span className="report-notice__filename">{reportFilename}</span>
      <button
        className="button button--secondary"
        onClick={handleDownload}
        type="button"
        disabled={downloadStatus === "downloading"}
      >
        {buttonLabel}
      </button>
      {downloadError ? (
        <p className="report-notice__error" role="alert">
          {downloadError}
        </p>
      ) : null}
>>>>>>> dev
    </section>
  );
}
