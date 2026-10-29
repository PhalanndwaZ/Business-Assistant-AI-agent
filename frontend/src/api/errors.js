const STATUS_MESSAGES = {
  401: "Your session has expired. Please log in again.",
  404: "That conversation is no longer available, so a new one was started.",
  422: "Please enter a question.",
  429: "You're sending requests too quickly.",
  502: "The AI model providers are unavailable right now. Try again in a moment.",
  503: "A required service isn't available. Check that the backend is running and configured.",
};

const NETWORK_MESSAGE = "Can't reach the API. Is the backend running?";
const GENERIC_MESSAGE = "Something went wrong. Please try again.";
const TIMEOUT_MESSAGE = "The request took too long. Please try again.";

/** Create a safe error object for API failures without exposing response text. */
export class ApiRequestError extends Error {
  /** Store the user-facing message and the failure category for later handling. */
  constructor(message, { kind, status = null, retryAfter = null } = {}) {
    super(message);
    this.name = "ApiRequestError";
    this.kind = kind;
    this.status = status;
    this.retryAfter = retryAfter;
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
  retryAfter = null,
} = {}) {
  let kind = "http";
  let message = STATUS_MESSAGES[status] || GENERIC_MESSAGE;
  const detail =
    body !== null &&
    typeof body === "object" &&
    typeof body.detail === "string"
      ? body.detail
      : null;

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
  } else if (
    status === 503 &&
    detail === "The question-answering service is not configured."
  ) {
    message =
      "The AI service is not configured. Add MISTRAL_API_KEY and either GROQ_API_KEY or INCEPTION_API_KEY to the project root .env file, then restart the backend.";
  }

  if (import.meta.env?.DEV) {
    console.error("API request failed", {
      status,
      kind,
      bodyShape: getBodyShape(body),
      causeType: cause?.name || null,
    });
  }

  return new ApiRequestError(message, { kind, status, retryAfter });
}
