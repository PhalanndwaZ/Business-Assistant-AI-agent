const ACTIVE_CONVERSATION_KEY_PREFIX = "business-analyst-ai:user-active:";
const CONVERSATION_KEY_PREFIX = "business-analyst-ai:user-conversation:";
const RECENT_CONVERSATIONS_KEY_PREFIX = "business-analyst-ai:user-recent:";
const LEGACY_ACTIVE_CONVERSATION_KEY =
  "business-analyst-ai:active-conversation";
const LEGACY_CONVERSATION_KEY_PREFIX = "business-analyst-ai:conversation:";
const LEGACY_RECENT_CONVERSATIONS_KEY =
  "business-analyst-ai:recent-conversations";
const MAX_RECENT_CONVERSATIONS = 15;
const memoryStorage = new Map();

/** Build the active-conversation key scoped to a user ID. */
function getActiveConversationKey(userId) {
  return `${ACTIVE_CONVERSATION_KEY_PREFIX}${encodeURIComponent(userId)}`;
}

/** Build a stored-conversation key scoped to its owner and conversation ID. */
function getConversationKey(userId, conversationId) {
  return `${CONVERSATION_KEY_PREFIX}${encodeURIComponent(userId)}:${encodeURIComponent(conversationId)}`;
}

/** Build the recent-conversations key scoped to a user ID. */
function getRecentConversationsKey(userId) {
  return `${RECENT_CONVERSATIONS_KEY_PREFIX}${encodeURIComponent(userId)}`;
}

/** Read a value from localStorage and fall back to the in-memory copy. */
function readStorageValue(key) {
  try {
    const stored = window.localStorage.getItem(key);
    if (stored !== null) {
      memoryStorage.set(key, stored);
      return stored;
    }
  } catch (error) {
    logStorageFailure("read", error);
  }
  return memoryStorage.get(key) || null;
}

/** Save a value in memory and best-effort localStorage. */
function writeStorageValue(key, value) {
  memoryStorage.set(key, value);
  try {
    window.localStorage.setItem(key, value);
    return true;
  } catch (error) {
    logStorageFailure("write", error);
    return false;
  }
}

/** Remove a value from memory and best-effort localStorage. */
function removeStorageValue(key) {
  memoryStorage.delete(key);
  try {
    window.localStorage.removeItem(key);
    return true;
  } catch (error) {
    logStorageFailure("remove", error);
    return false;
  }
}

/** List browser and in-memory storage keys without leaking stored values. */
function listStorageKeys() {
  const keys = new Set(memoryStorage.keys());
  try {
    const storage = window.localStorage;
    for (let index = 0; index < storage.length; index += 1) {
      const key = storage.key(index);
      if (key) {
        keys.add(key);
      }
    }
  } catch (error) {
    logStorageFailure("list-keys", error);
  }
  return [...keys];
}

/** Check that a stored message has the fields used by the chat components. */
function isStoredMessage(message) {
  return (
    message !== null &&
    typeof message === "object" &&
    typeof message.id === "string" &&
    (message.role === "user" || message.role === "assistant") &&
    typeof message.content === "string" &&
    (message.role === "user" ||
      (message.response !== null && typeof message.response === "object"))
  );
}

/** Check the metadata needed to display one saved conversation in Recents. */
function isRecentConversation(conversation) {
  return (
    conversation !== null &&
    typeof conversation === "object" &&
    typeof conversation.conversationId === "string" &&
    typeof conversation.title === "string" &&
    Number.isFinite(conversation.updatedAt)
  );
}

/** Log a storage failure in development without exposing identifiers or data. */
function logStorageFailure(operation, error) {
  if (import.meta.env?.DEV) {
    console.error("Conversation storage failed", {
      operation,
      errorType: error?.name || "UnknownError",
    });
  }
}

/** Read a user's saved conversation summaries from scoped storage. */
function readRecentConversationsFromStorage(userId) {
  const serialized = readStorageValue(getRecentConversationsKey(userId));
  if (!serialized) {
    return [];
  }

  try {
    const stored = JSON.parse(serialized);
    if (!Array.isArray(stored)) {
      logStorageFailure("read-invalid-recents", new Error("Invalid stored data"));
      return [];
    }
    return stored
      .filter(isRecentConversation)
      .sort((left, right) => right.updatedAt - left.updatedAt);
  } catch (error) {
    logStorageFailure("parse-recents", error);
    return [];
  }
}

/** Return the newest saved conversation summaries for the sidebar. */
export function loadRecentConversations(userId) {
  if (typeof userId !== "string" || !userId) {
    return [];
  }
  return (
    readRecentConversationsFromStorage(userId).slice(
      0,
      MAX_RECENT_CONVERSATIONS,
    ) || []
  );
}

/** Create an updated, bounded list of recent conversation summaries. */
export function upsertRecentConversation(
  conversations,
  conversationId,
  messages,
  updatedAt = Date.now(),
) {
  if (!conversationId || !Array.isArray(messages)) {
    return conversations;
  }

  const firstUserMessage = messages.find(
    (message) => message.role === "user" && message.content.trim(),
  );
  if (!firstUserMessage) {
    return conversations;
  }

  const questionTitle = firstUserMessage.content.trim().replace(/\s+/g, " ");
  const title =
    questionTitle.length > 96
      ? `${questionTitle.slice(0, 93).trimEnd()}...`
      : questionTitle;
  const updated = [
    { conversationId, title, updatedAt },
    ...conversations.filter(
      (conversation) => conversation.conversationId !== conversationId,
    ),
  ];
  return updated
    .sort((left, right) => right.updatedAt - left.updatedAt)
    .slice(0, MAX_RECENT_CONVERSATIONS);
}

/** Parse one stored conversation after validating its complete message shape. */
function parseStoredConversation(conversationId, serialized) {
  try {
    const stored = JSON.parse(serialized);
    if (
      stored === null ||
      typeof stored !== "object" ||
      stored.conversationId !== conversationId ||
      !Array.isArray(stored.messages) ||
      !stored.messages.every(isStoredMessage)
    ) {
      logStorageFailure("read-invalid-data", new Error("Invalid stored data"));
      return null;
    }

    return { conversationId, messages: stored.messages };
  } catch (error) {
    logStorageFailure("parse", error);
    return null;
  }
}

/** Read and validate a conversation without changing which one is active. */
function readStoredConversation(userId, conversationId) {
  const serialized = readStorageValue(
    getConversationKey(userId, conversationId),
  );
  if (!serialized) {
    return null;
  }
  return parseStoredConversation(conversationId, serialized);
}

/** Load the active conversation and its displayed messages from local storage. */
export function loadConversation(userId) {
  if (typeof userId !== "string" || !userId) {
    return null;
  }
  const conversationId = readStorageValue(getActiveConversationKey(userId));
  if (!conversationId) {
    return null;
  }

  const conversation = readStoredConversation(userId, conversationId);
  if (!conversation) {
    return { conversationId, messages: [] };
  }

  const recents = loadRecentConversations(userId);
  if (
    conversation.messages.some((message) => message.role === "user") &&
    !recents.some((item) => item.conversationId === conversationId)
  ) {
    saveConversation(userId, conversationId, conversation.messages);
  }
  return conversation;
}

/** Load a saved conversation and make it active for follow-up questions. */
export function loadConversationById(userId, conversationId) {
  if (
    typeof userId !== "string" ||
    !userId ||
    typeof conversationId !== "string" ||
    !conversationId
  ) {
    return null;
  }

  const conversation = readStoredConversation(userId, conversationId);
  if (!conversation) {
    return null;
  }
  writeStorageValue(getActiveConversationKey(userId), conversationId);
  return conversation;
}

/** Persist the active conversation ID and its displayed messages locally. */
export function saveConversation(userId, conversationId, messages) {
  if (
    typeof userId !== "string" ||
    !userId ||
    !conversationId ||
    !Array.isArray(messages)
  ) {
    return false;
  }

  const existingRecents = readRecentConversationsFromStorage(userId);
  writeStorageValue(getActiveConversationKey(userId), conversationId);
  writeStorageValue(
    getConversationKey(userId, conversationId),
    JSON.stringify({ conversationId, messages }),
  );

  const nextRecents = upsertRecentConversation(
    existingRecents,
    conversationId,
    messages,
  );
  writeStorageValue(
    getRecentConversationsKey(userId),
    JSON.stringify(nextRecents),
  );
  const retainedIds = new Set(
    nextRecents.map((conversation) => conversation.conversationId),
  );
  for (const conversation of existingRecents) {
    if (!retainedIds.has(conversation.conversationId)) {
      removeStorageValue(
        getConversationKey(userId, conversation.conversationId),
      );
    }
  }
  return true;
}

/** Clear only the active selection so saved chats remain available in Recents. */
export function clearActiveConversation(userId) {
  if (typeof userId !== "string" || !userId) {
    return false;
  }
  return removeStorageValue(getActiveConversationKey(userId));
}

/** Delete a saved conversation and its sidebar entry from local storage. */
export function clearConversation(userId, conversationId = null) {
  if (typeof userId !== "string" || !userId) {
    return false;
  }
  const existingRecents = readRecentConversationsFromStorage(userId);
  const activeKey = getActiveConversationKey(userId);
  const activeConversationId = readStorageValue(activeKey);
  const conversationToClear = conversationId || activeConversationId;
  if (conversationToClear) {
    removeStorageValue(getConversationKey(userId, conversationToClear));
  }
  if (!conversationId || activeConversationId === conversationId) {
    removeStorageValue(activeKey);
  }
  if (conversationToClear) {
    const nextRecents = existingRecents.filter(
      (conversation) => conversation.conversationId !== conversationToClear,
    );
    writeStorageValue(
      getRecentConversationsKey(userId),
      JSON.stringify(nextRecents),
    );
  }
  return true;
}

/** Remove saved messages, recents, and active selection for one user. */
export function clearUserConversations(userId) {
  if (typeof userId !== "string" || !userId) {
    return false;
  }
  const userIdPrefix = `${CONVERSATION_KEY_PREFIX}${encodeURIComponent(userId)}:`;
  const activeKey = getActiveConversationKey(userId);
  const recentKey = getRecentConversationsKey(userId);
  try {
    for (const key of listStorageKeys()) {
      if (
        key === activeKey ||
        key === recentKey ||
        key.startsWith(userIdPrefix)
      ) {
        removeStorageValue(key);
      }
    }
    return true;
  } catch (error) {
    logStorageFailure("clear-user", error);
    return false;
  }
}

/** Delete pre-auth conversation keys so they cannot cross user sessions. */
export function clearLegacyConversationData() {
  try {
    for (const key of listStorageKeys()) {
      if (
        key === LEGACY_ACTIVE_CONVERSATION_KEY ||
        key === LEGACY_RECENT_CONVERSATIONS_KEY ||
        key.startsWith(LEGACY_CONVERSATION_KEY_PREFIX)
      ) {
        removeStorageValue(key);
      }
    }
    return true;
  } catch (error) {
    logStorageFailure("clear-legacy", error);
    return false;
  }
}
