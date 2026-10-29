import { USE_MOCK } from "../config.js";
import { requestBlob } from "./client.js";
import { ApiRequestError } from "./errors.js";

const SAFE_REPORT_FILENAME_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._-]*\.docx$/i;

/** Check the strict filename contract shared by report UI and downloads. */
export function isSafeReportFilename(filename) {
  return (
    typeof filename === "string" &&
    SAFE_REPORT_FILENAME_PATTERN.test(filename)
  );
}

/** Fetch a report with the current token and prompt the browser to save it. */
export async function downloadReport(filename, { signal } = {}) {
  if (!isSafeReportFilename(filename)) {
    throw new TypeError("The report filename is invalid.");
  }
  if (USE_MOCK) {
    throw new ApiRequestError("Report downloads are unavailable in mock mode.", {
      kind: "mock-unavailable",
    });
  }

  let report;
  try {
    report = await requestBlob(`/reports/${encodeURIComponent(filename)}`, {
      signal,
    });
  } catch (error) {
    if (error instanceof ApiRequestError && error.status === 404) {
      throw new ApiRequestError("Report not found.", {
        kind: "http",
        status: 404,
      });
    }
    throw error;
  }

  const objectUrl = URL.createObjectURL(report);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  link.hidden = true;
  try {
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
  }
}
