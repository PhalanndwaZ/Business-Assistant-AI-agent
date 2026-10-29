/** Base path used for same-origin API requests through the Vite proxy. */
export const API_BASE = import.meta.env?.VITE_API_BASE || "/api";

/** Enable fixture responses instead of making requests to the backend. */
export const USE_MOCK = import.meta.env?.VITE_USE_MOCK === "true";

/** Show demo usernames on the login screen only when explicitly enabled. */
export const SHOW_DEMO_ACCOUNTS =
  import.meta.env?.VITE_SHOW_DEMO_ACCOUNTS === "true";

/** Demo usernames shown in the optional login help panel; passwords are omitted. */
export const DEMO_USERNAMES = [
  "sales.demo",
  "newuser.demo",
  "hr.demo",
  "manager.demo",
  "admin.demo",
];

/** Request timeout in milliseconds for the slowest expected answer workflow. */
export const REQUEST_TIMEOUT_MS = 120_000;

/** Soft limit for user questions, measured in JavaScript characters. */
export const QUESTION_LENGTH_LIMIT = 1_000;

/** Suggested questions shown for each role; the backend remains authoritative. */
export const STARTER_QUESTIONS_BY_ROLE = {
  sales: [
    "Revenue for November 2024?",
    "Top customers in 2024?",
    "Was December's revenue drop unusual?",
  ],
  hr: [
    "Headcount by department?",
    "What does the leave policy say?",
  ],
  manager: [
    "Give me a sales decline risk report for December 2024.",
    "Headcount by department?",
    "What changed in December revenue, and what did management report?",
  ],
  admin: [],
};
