import { loadAuthToken } from "../auth/authStore.js";
import { API_BASE } from "../config.js";
import { normalizeApiError } from "./errors.js";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE.replace(/\/+$/, "")}${path}`, {
    ...options,
    headers: {
      Authorization: "Bearer " + loadAuthToken(),
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok) {
    throw normalizeApiError({ status: response.status, body: payload });
  }
  return payload;
}

export function listDrafts(conversationId) {
  return request(`/drafts?conversation_id=${encodeURIComponent(conversationId)}`);
}

export function updateDraft(draftId, patch) {
  return request(`/drafts/${encodeURIComponent(draftId)}`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}
