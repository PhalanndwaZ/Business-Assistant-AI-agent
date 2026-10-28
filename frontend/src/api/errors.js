const STATUS_MESSAGES = {
  422: "Please enter a question.",
  502: "The AI model providers are unavailable right now. Try again in a moment.",
  503: "A required service isn't available. Check that the backend is running and configured.",
};

const NETWORK_MESSAGE = "Can't reach the API. Is the backend running?";
const GENERIC_MESSAGE = "Something went wrong. Please try again.";
const TIMEOUT_MESSAGE = "The request took too long. Please try again.";

/** Create a safe error object for API failures without exposing response text. */
export class ApiRequestError extends Error {
  /** Store the user-facing message and the failure category for later handling. */
  constructor(message, { kind, status = null } = {}) {
    super(message);
    this.name = "ApiRequestError";
    this.kind = kind;
    this.status = status;
  }
}

/** Describe the shape of an error body without logging its contents. */
function getBodyShape(body) {
  if (body === null || body === undefined) {
    return "empty";
  }
  if (typeof body === "string") {
    return "string";
  }
  if (Array.isArray(body)) {
    return "array";
  }
  if (typeof body === "object" && Array.isArray(body.detail)) {
    return "detail-list";
  }
  if (typeof body === "object" && typeof body.detail === "string") {
    return "detail-string";
  }
  return "object";
}

/** Normalize status, network, timeout, cancellation, and malformed-response errors. */
export function normalizeApiError({
  status = null,
  body = null,
  cause = null,
  cancelled = false,
  timedOut = false,
  networkFailure = false,
  invalidResponse = false,
} = {}) {
  let kind = "http";
  let message = STATUS_MESSAGES[status] || GENERIC_MESSAGE;

  if (cancelled) {
    kind = "cancelled";
    message = "Cancelled";
  } else if (timedOut) {
    kind = "timeout";
    message = TIMEOUT_MESSAGE;
  } else if (networkFailure) {
    kind = "network";
    message = NETWORK_MESSAGE;
  } else if (invalidResponse) {
    kind = "invalid-response";
  } else if (!Number.isInteger(status)) {
    kind = "network";
    message = NETWORK_MESSAGE;
  }

  if (import.meta.env?.DEV) {
    console.error("API request failed", {
      status,
      kind,
      bodyShape: getBodyShape(body),
      causeType: cause?.name || null,
    });
  }

  return new ApiRequestError(message, { kind, status });
}
