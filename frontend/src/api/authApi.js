import { requestJson } from "./client.js";
import { ApiRequestError, normalizeApiError } from "./errors.js";

const VALID_ROLES = new Set(["sales", "hr", "manager", "admin"]);

/** Check the token fields returned by the login endpoint. */
function isLoginResponse(payload) {
  return (
    payload !== null &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    typeof payload.access_token === "string" &&
    payload.access_token.length > 0 &&
    payload.token_type === "bearer" &&
    Number.isInteger(payload.expires_in) &&
    payload.expires_in > 0
  );
}

/** Check the identity fields returned by the authenticated profile endpoint. */
function isUserResponse(payload) {
  return (
    payload !== null &&
    typeof payload === "object" &&
    !Array.isArray(payload) &&
    typeof payload.user_id === "string" &&
    typeof payload.username === "string" &&
    typeof payload.name === "string" &&
    VALID_ROLES.has(payload.role)
  );
}

/** Authenticate with a username and password without exposing error details. */
export async function login(username, password) {
  let payload;
  try {
    payload = await requestJson("/auth/login", {
      method: "POST",
      body: { username, password },
      authenticated: false,
    });
  } catch (error) {
    if (error?.status === 401) {
      throw new ApiRequestError("Incorrect username or password", {
        kind: "authentication",
        status: 401,
      });
    }
    if (error?.status === 429) {
      throw new ApiRequestError("Too many attempts. Try again shortly.", {
        kind: "rate-limit",
        status: 429,
        retryAfter: error.retryAfter,
      });
    }
    throw error;
  }
  if (!isLoginResponse(payload)) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}

/** Fetch the identity attached to the current bearer token. */
export async function getMe({ signal } = {}) {
  const payload = await requestJson("/me", {
    signal,
    authenticated: true,
  });
  if (!isUserResponse(payload)) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}
