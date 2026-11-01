import { loadAuthToken } from "../auth/authStore.js";
import { API_BASE, USE_MOCK } from "../config.js";
import { normalizeApiError } from "./errors.js";

async function readJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

function authorizationHeaders() {
  return { Authorization: "Bearer " + loadAuthToken() };
}

export async function uploadDocument(file, conversationId = null) {
  if (USE_MOCK) {
    return {
      conversation_id: conversationId || crypto.randomUUID(),
      document_id: crypto.randomUUID(),
      name: file.name,
      pages: 1,
      chunks: 1,
      status: "ready",
    };
  }
  const body = new FormData();
  body.append("file", file);
  if (conversationId) {
    body.append("conversation_id", conversationId);
  }
  const response = await fetch(`${API_BASE.replace(/\/+$/, "")}/documents`, {
    method: "POST",
    headers: authorizationHeaders(),
    body,
  });
  const payload = await readJson(response);
  if (!response.ok) {
    throw normalizeApiError({ status: response.status, body: payload });
  }
  return payload;
}

export async function listDocuments(conversationId) {
  const response = await fetch(
    `${API_BASE.replace(/\/+$/, "")}/conversations/${conversationId}/documents`,
    { headers: authorizationHeaders() },
  );
  const payload = await readJson(response);
  if (!response.ok) {
    throw normalizeApiError({ status: response.status, body: payload });
  }
  return payload;
}

export async function deleteDocument(conversationId, documentId) {
  const response = await fetch(
    `${API_BASE.replace(/\/+$/, "")}/conversations/${conversationId}/documents/${documentId}`,
    { method: "DELETE", headers: authorizationHeaders() },
  );
  if (!response.ok) {
    const payload = await readJson(response);
    throw normalizeApiError({ status: response.status, body: payload });
  }
}
