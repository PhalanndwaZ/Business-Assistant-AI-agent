import { requestJson } from "./client.js";
import { normalizeApiError } from "./errors.js";

const VALID_ROLES = new Set(["sales", "hr", "manager", "admin"]);

/** Validate safe account metadata returned by the admin endpoints. */
function isAdminUser(payload) {
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

/** List registered account metadata without exposing password hashes. */
export async function listAdminUsers({ signal } = {}) {
  const payload = await requestJson("/admin/users", { signal });
  if (!Array.isArray(payload) || !payload.every(isAdminUser)) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}

/** Register an account using the administrator-provided initial password. */
export async function createAdminUser(user, { signal } = {}) {
  const payload = await requestJson("/admin/users", {
    method: "POST",
    body: user,
    signal,
  });
  if (!isAdminUser(payload)) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}
