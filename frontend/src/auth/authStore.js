const TOKEN_KEY = "business-analyst-ai:auth-token";
const USER_KEY = "business-analyst-ai:auth-user";
const PENDING_QUESTION_KEY = "business-analyst-ai:pending-question";
const VALID_ROLES = new Set(["sales", "hr", "manager", "admin"]);

let memorySession = null;
let hasMemorySessionOverride = false;
let memoryPendingQuestion = null;
let hasMemoryPendingQuestionOverride = false;

/** Check that a user record contains the fields used by authenticated UI. */
function isAuthUser(user) {
  return (
    user !== null &&
    typeof user === "object" &&
    typeof user.user_id === "string" &&
    typeof user.username === "string" &&
    typeof user.name === "string" &&
    VALID_ROLES.has(user.role)
  );
}

/** Log storage failures in development without exposing tokens or user data. */
function logStorageFailure(operation, error) {
  if (import.meta.env?.DEV) {
    console.error("Authentication storage failed", {
      operation,
      errorType: error?.name || "UnknownError",
    });
  }
}

/** Read one session value while tolerating unavailable browser storage. */
function readSessionValue(key) {
  try {
    return window.sessionStorage.getItem(key);
  } catch (error) {
    logStorageFailure("read", error);
    return null;
  }
}

/** Write one session value while tolerating unavailable browser storage. */
function writeSessionValue(key, value) {
  try {
    window.sessionStorage.setItem(key, value);
  } catch (error) {
    logStorageFailure("write", error);
  }
}

/** Remove one session value while tolerating unavailable browser storage. */
function removeSessionValue(key) {
  try {
    window.sessionStorage.removeItem(key);
  } catch (error) {
    logStorageFailure("remove", error);
  }
}

/** Load the session-only bearer token, using memory if storage is unavailable. */
export function loadAuthToken() {
  if (hasMemorySessionOverride) {
    return memorySession?.accessToken || null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  return readSessionValue(TOKEN_KEY);
}

/** Load the session-only user profile, using memory if storage is unavailable. */
export function loadAuthUser() {
  if (hasMemorySessionOverride) {
    return memorySession?.user || null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const serializedUser = readSessionValue(USER_KEY);
  if (!serializedUser) {
    return null;
  }
  try {
    const user = JSON.parse(serializedUser);
    return isAuthUser(user) ? user : null;
  } catch (error) {
    logStorageFailure("parse-user", error);
    return null;
  }
}

/** Load the unsent question saved for the user whose session expired. */
export function loadPendingQuestion() {
  if (hasMemoryPendingQuestionOverride) {
    return memoryPendingQuestion ? { ...memoryPendingQuestion } : null;
  }
  if (typeof window === "undefined") {
    return null;
  }
  const serializedQuestion = readSessionValue(PENDING_QUESTION_KEY);
  if (!serializedQuestion) {
    return null;
  }
  try {
    const pending = JSON.parse(serializedQuestion);
    if (
      pending !== null &&
      typeof pending === "object" &&
      typeof pending.question === "string" &&
      pending.question.trim() &&
      typeof pending.userId === "string" &&
      pending.userId
    ) {
      memoryPendingQuestion = {
        question: pending.question,
        userId: pending.userId,
      };
      return { ...memoryPendingQuestion };
    }
    return null;
  } catch (error) {
    logStorageFailure("parse-pending-question", error);
    return null;
  }
}

/** Save one unsent question without coupling it to the bearer token. */
export function savePendingQuestion(question, userId) {
  if (
    typeof question !== "string" ||
    !question.trim() ||
    typeof userId !== "string" ||
    !userId
  ) {
    return false;
  }
  memoryPendingQuestion = { question: question.trim(), userId };
  hasMemoryPendingQuestionOverride = true;
  writeSessionValue(
    PENDING_QUESTION_KEY,
    JSON.stringify(memoryPendingQuestion),
  );
  return true;
}

/** Discard the saved question after it is resent, dismissed, or signed out. */
export function clearPendingQuestion() {
  memoryPendingQuestion = null;
  hasMemoryPendingQuestionOverride = true;
  removeSessionValue(PENDING_QUESTION_KEY);
}

/** Save a token and optional verified user in sessionStorage and memory. */
export function saveAuthSession(accessToken, user = null) {
  if (typeof accessToken !== "string" || !accessToken) {
    throw new TypeError("An access token is required to save an auth session.");
  }
  if (user !== null && !isAuthUser(user)) {
    throw new TypeError("The authenticated user profile is invalid.");
  }

  memorySession = { accessToken, user };
  hasMemorySessionOverride = true;
  if (typeof window === "undefined") {
    return;
  }
  writeSessionValue(TOKEN_KEY, accessToken);
  if (user === null) {
    removeSessionValue(USER_KEY);
    return;
  }
  writeSessionValue(USER_KEY, JSON.stringify(user));
}

/** Clear the auth session from storage and prevent stale memory fallbacks. */
export function clearAuthSession() {
  memorySession = null;
  hasMemorySessionOverride = true;
  if (typeof window === "undefined") {
    return;
  }
  removeSessionValue(TOKEN_KEY);
  removeSessionValue(USER_KEY);
}
