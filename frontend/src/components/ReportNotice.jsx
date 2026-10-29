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
    return null;
  }

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
    </section>
  );
}
