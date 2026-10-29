import { API_BASE, REQUEST_TIMEOUT_MS, USE_MOCK } from "../config.js";
import {
  clearAuthSession,
  loadAuthToken,
  loadAuthUser,
} from "../auth/authStore.js";
import { ApiRequestError, normalizeApiError } from "./errors.js";

const SESSION_EXPIRED_EVENT = "business-analyst-ai:session-expired";

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
    (!Object.hasOwn(payload, "charts") || Array.isArray(payload.charts)) &&
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

/** Convert Retry-After seconds or an HTTP date into a delay in seconds. */
function parseRetryAfter(headerValue) {
  if (!headerValue) {
    return null;
  }
  const seconds = Number(headerValue);
  if (Number.isFinite(seconds) && seconds >= 0) {
    return seconds;
  }
  const retryAt = Date.parse(headerValue);
  return Number.isFinite(retryAt)
    ? Math.max(0, Math.ceil((retryAt - Date.now()) / 1000))
    : null;
}

/** Remove an invalid session and notify the auth provider without exposing it. */
function expireAuthenticatedSession(question = null) {
  if (typeof window !== "undefined") {
    window.dispatchEvent(
      new CustomEvent(SESSION_EXPIRED_EVENT, {
        detail: {
          question:
            typeof question === "string" && question.trim()
              ? question.trim()
              : null,
          userId: loadAuthUser()?.user_id || null,
        },
      }),
    );
  }
  clearAuthSession();
}

/**
 * Send a JSON API request with optional bearer authentication and safe errors.
 */
export async function requestJson(
  path,
  {
    method = "GET",
    body,
    headers = {},
    signal,
    authenticated = true,
  } = {},
) {
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
    const requestHeaders = new Headers(headers);
    let requestBody;
    if (body !== undefined) {
      requestHeaders.set("Content-Type", "application/json");
      requestBody = typeof body === "string" ? body : JSON.stringify(body);
    }
    if (authenticated) {
      const accessToken = loadAuthToken();
      if (accessToken) {
        requestHeaders.set("Authorization", `Bearer ${accessToken}`);
      }
    }

    const response = await fetch(`${apiBase}${path}`, {
      method,
      headers: requestHeaders,
      body: requestBody,
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
      if (authenticated && response.status === 401) {
        expireAuthenticatedSession(
          path === "/ask" && body && typeof body === "object"
            ? body.question
            : null,
        );
      }
      throw normalizeApiError({
        status: response.status,
        body: payload,
        networkFailure: isProxyUnavailableResponse(response),
        retryAfter:
          response.status === 429
            ? parseRetryAfter(response.headers.get("Retry-After"))
            : null,
      });
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

/**
 * Fetch a binary API response using the current bearer token.
 */
export async function requestBlob(path, { signal } = {}) {
  const controller = new AbortController();
  const timeoutState = { timedOut: false };
  const apiBase = API_BASE.replace(/\/+$/, "");

  function handleTimeout() {
    abortOnTimeout(controller, timeoutState);
  }

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
    const requestHeaders = new Headers();
    const accessToken = loadAuthToken();
    if (accessToken) {
      requestHeaders.set("Authorization", `Bearer ${accessToken}`);
    }

    const response = await fetch(`${apiBase}${path}`, {
      method: "GET",
      headers: requestHeaders,
      signal: controller.signal,
    });

    if (signal?.aborted) {
      throw normalizeApiError({ cancelled: true });
    }
    if (timeoutState.timedOut) {
      throw normalizeApiError({ timedOut: true });
    }
    if (!response.ok) {
      const payload = await readResponseBody(response);
      if (response.status === 401) {
        expireAuthenticatedSession();
      }
      throw normalizeApiError({
        status: response.status,
        body: payload,
        networkFailure: isProxyUnavailableResponse(response),
      });
    }
    return await response.blob();
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
    try {
      return await askMockQuestion({ question, conversationId, signal });
    } catch (error) {
      if (error instanceof ApiRequestError && error.status === 401) {
        expireAuthenticatedSession(question);
      }
      throw error;
    }
  }

  const payload = await requestJson("/ask", {
    method: "POST",
    body: {
      question: typeof question === "string" ? question.trim() : "",
      conversation_id: conversationId,
    },
    signal,
    authenticated: true,
  });
  if (!isAskResponse(payload)) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}
