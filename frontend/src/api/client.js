import { API_BASE, REQUEST_TIMEOUT_MS, USE_MOCK } from "../config.js";
import { ApiRequestError, normalizeApiError } from "./errors.js";

/** Read a JSON response body without assuming that every response is JSON. */
async function readResponseBody(response) {
  try {
    const text = await response.text();
    if (!text) {
      return null;
    }
    try {
      return JSON.parse(text);
    } catch {
      return text;
    }
  } catch {
    return null;
  }
}

/** Recognize non-JSON 5xx responses emitted when the Vite proxy cannot connect. */
function isProxyUnavailableResponse(response) {
  const contentType = response.headers.get("content-type") || "";
  return (
    response.status >= 500 &&
    !contentType.toLowerCase().includes("application/json")
  );
}

/** Confirm a successful response matches the documented ask endpoint contract. */
function isAskResponse(payload) {
  return (
    payload !== null &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    typeof payload.answer === "string" &&
    typeof payload.conversation_id === "string" &&
    Array.isArray(payload.figures) &&
    Array.isArray(payload.sources) &&
    Array.isArray(payload.caveats) &&
    (!Object.hasOwn(payload, "report_filename") ||
      payload.report_filename === null ||
      typeof payload.report_filename === "string")
  );
}

/** Forward the caller's cancellation signal to the request controller. */
function forwardAbort(controller) {
  controller.abort();
}

/** Abort the request when its configured time budget expires. */
function abortOnTimeout(controller, timeoutState) {
  timeoutState.timedOut = true;
  controller.abort();
}

/**
 * Ask the backend a question and return its validated response payload.
 *
 * The request body uses the backend's snake_case `conversation_id` field.
 */
export async function askQuestion({
  question,
  conversationId = null,
  signal,
} = {}) {
  if (USE_MOCK) {
    const { askMockQuestion } = await import("./mockClient.js");
    return askMockQuestion({ question, conversationId, signal });
  }

  const controller = new AbortController();
  const timeoutState = { timedOut: false };
  const apiBase = API_BASE.replace(/\/+$/, "");

  /** Abort this request after its configured time budget expires. */
  function handleTimeout() {
    abortOnTimeout(controller, timeoutState);
  }

  /** Abort this request when the caller's signal is triggered. */
  function handleAbort() {
    forwardAbort(controller);
  }

  const timeoutId = setTimeout(handleTimeout, REQUEST_TIMEOUT_MS);

  if (signal?.aborted) {
    handleAbort();
  } else {
    signal?.addEventListener("abort", handleAbort, { once: true });
  }

  try {
    const response = await fetch(`${apiBase}/ask`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        question: typeof question === "string" ? question.trim() : "",
        conversation_id: conversationId,
      }),
      signal: controller.signal,
    });
    const payload = await readResponseBody(response);

    if (signal?.aborted) {
      throw normalizeApiError({ cancelled: true });
    }
    if (timeoutState.timedOut) {
      throw normalizeApiError({ timedOut: true });
    }

    if (!response.ok) {
      throw normalizeApiError({
        status: response.status,
        body: payload,
        networkFailure: isProxyUnavailableResponse(response),
      });
    }

    if (!isAskResponse(payload)) {
      throw normalizeApiError({ body: payload, invalidResponse: true });
    }

    return payload;
  } catch (error) {
    if (error instanceof ApiRequestError) {
      throw error;
    }
    if (signal?.aborted) {
      throw normalizeApiError({ cancelled: true, cause: error });
    }
    if (timeoutState.timedOut) {
      throw normalizeApiError({ timedOut: true, cause: error });
    }
    throw normalizeApiError({ cause: error });
  } finally {
    clearTimeout(timeoutId);
    signal?.removeEventListener("abort", handleAbort);
  }
}
