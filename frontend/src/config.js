/** Base path used for same-origin API requests through the Vite proxy. */
export const API_BASE = import.meta.env?.VITE_API_BASE || "/api";

/** Enable fixture responses instead of making requests to the backend. */
export const USE_MOCK = import.meta.env?.VITE_USE_MOCK === "true";

/** Request timeout in milliseconds for the slowest expected answer workflow. */
export const REQUEST_TIMEOUT_MS = 120_000;

/** Soft limit for user questions, measured in JavaScript characters. */
export const QUESTION_LENGTH_LIMIT = 1_000;

/** Suggested questions shown in the empty conversation state. */
export const EXAMPLE_QUESTIONS = [
  "How did completed-order revenue change from November to December 2024?",
  "What is the reporting window for a damaged product?",
  "What changed in December revenue, and what factors did management report?",
];
