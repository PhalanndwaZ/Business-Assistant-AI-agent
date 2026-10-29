import combinedFixture from "../../mock/fixtures/combined.json" with {
  type: "json",
};
import documentFixture from "../../mock/fixtures/document.json" with {
  type: "json",
};
import followUpFixture from "../../mock/fixtures/follow-up.json" with {
  type: "json",
};
import reportFixture from "../../mock/fixtures/report.json" with {
  type: "json",
};
import structuredFixture from "../../mock/fixtures/structured.json" with {
  type: "json",
};
import salesResponsesFixture from "../../mock/fixtures/sales/responses.json" with {
  type: "json",
};
import unanswerableFixture from "../../mock/fixtures/unanswerable.json" with {
  type: "json",
};
import validationFixture from "../../mock/fixtures/validation-422.json" with {
  type: "json",
};

import { normalizeApiError } from "./errors.js";

const FIXTURES = {
  combined: combinedFixture,
  document: documentFixture,
  "follow-up": followUpFixture,
  report: reportFixture,
  structured: structuredFixture,
  unanswerable: unanswerableFixture,
  "validation-422": validationFixture,
};

const ERROR_FIXTURES = salesResponsesFixture.errors;

/** Match known sample prompts to their captured responses. */
function getFixtureName(question) {
  const normalized = typeof question === "string" ? question.toLowerCase() : "";

  if (!normalized.trim()) {
    return "validation-422";
  }
  if (
    normalized.includes("reporting window") &&
    normalized.includes("damaged product")
  ) {
    return "document";
  }
  if (
    normalized.includes("management") &&
    normalized.includes("december revenue")
  ) {
    return "combined";
  }
  if (
    normalized.includes("those november and december") ||
    normalized.includes("november and december revenue totals")
  ) {
    return "follow-up";
  }
  if (normalized.includes("report") && normalized.includes("november")) {
    return "report";
  }
  if (
    normalized.includes("completed-order revenue") &&
    normalized.includes("november") &&
    normalized.includes("december")
  ) {
    return "structured";
  }
  return "unanswerable";
}

/** Return a selected saved response while preserving mock conversation state. */
export async function askMockFixture(
  fixtureName,
  { conversationId = null, signal } = {},
) {
  if (signal?.aborted) {
    throw normalizeApiError({ cancelled: true });
  }

  const fixture = FIXTURES[fixtureName];
  if (!fixture) {
    throw normalizeApiError({ invalidResponse: true });
  }
  if (fixtureName === "validation-422") {
    throw normalizeApiError({ status: 422, body: fixture });
  }

  await Promise.resolve();
  if (signal?.aborted) {
    throw normalizeApiError({ cancelled: true });
  }

  return {
    ...fixture,
    conversation_id: conversationId || crypto.randomUUID(),
  };
}

/** Select a saved fixture based on the submitted sample question. */
export function askMockQuestion({ question, conversationId = null, signal }) {
  const normalizedQuestion =
    typeof question === "string" ? question.trim().toLowerCase() : "";

  if (normalizedQuestion === "mock 401") {
    throw normalizeApiError({
      status: ERROR_FIXTURES.unauthorized.status,
      body: ERROR_FIXTURES.unauthorized.body,
    });
  }
  if (normalizedQuestion === "mock 429") {
    throw normalizeApiError({
      status: ERROR_FIXTURES.rate_limited.status,
      body: ERROR_FIXTURES.rate_limited.body,
      retryAfter: Number(
        ERROR_FIXTURES.rate_limited.headers["Retry-After"],
      ),
    });
  }
  if (normalizedQuestion === "mock 404" && conversationId) {
    throw normalizeApiError({
      status: ERROR_FIXTURES.conversation_not_found.status,
      body: ERROR_FIXTURES.conversation_not_found.body,
    });
  }

  return askMockFixture(getFixtureName(question), {
    conversationId,
    signal,
  });
}
