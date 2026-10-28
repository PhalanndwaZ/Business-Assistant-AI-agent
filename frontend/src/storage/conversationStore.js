const ACTIVE_CONVERSATION_KEY = "business-analyst-ai:active-conversation";
const CONVERSATION_KEY_PREFIX = "business-analyst-ai:conversation:";
const RECENT_CONVERSATIONS_KEY = "business-analyst-ai:recent-conversations";
const MAX_RECENT_CONVERSATIONS = 15;

/** Build the storage key for one private conversation identifier. */
function getConversationKey(conversationId) {
  return `${CONVERSATION_KEY_PREFIX}${encodeURIComponent(conversationId)}`;
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

/** Read saved conversation summaries, returning null when storage is blocked. */
function readRecentConversationsFromStorage() {
  let serialized;
  try {
    serialized = window.localStorage.getItem(RECENT_CONVERSATIONS_KEY);
  } catch (error) {
    logStorageFailure("read-recents", error);
    return null;
  }
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
export function loadRecentConversations() {
  return (
    readRecentConversationsFromStorage()?.slice(
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
function readStoredConversation(conversationId) {
  let serialized;
  try {
    serialized = window.localStorage.getItem(
      getConversationKey(conversationId),
    );
  } catch (error) {
    logStorageFailure("read-messages", error);
    return null;
  }
  if (!serialized) {
    return null;
  }
  return parseStoredConversation(conversationId, serialized);
}

/** Load the active conversation and its displayed messages from local storage. */
export function loadConversation() {
  let conversationId;
  try {
    conversationId = window.localStorage.getItem(
      ACTIVE_CONVERSATION_KEY,
    );
  } catch (error) {
    logStorageFailure("read", error);
    return null;
  }
  if (!conversationId) {
    return null;
  }

  const conversation = readStoredConversation(conversationId);
  if (!conversation) {
    return { conversationId, messages: [] };
  }

  const recents = loadRecentConversations();
  if (
    conversation.messages.some((message) => message.role === "user") &&
    !recents.some((item) => item.conversationId === conversationId)
  ) {
    saveConversation(conversationId, conversation.messages);
  }
  return conversation;
}

/** Load a saved conversation and make it active for follow-up questions. */
export function loadConversationById(conversationId) {
  if (typeof conversationId !== "string" || !conversationId) {
    return null;
  }

  const conversation = readStoredConversation(conversationId);
  if (!conversation) {
    return null;
  }
  try {
    window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
  } catch (error) {
    logStorageFailure("activate", error);
  }
  return conversation;
}

/** Persist the active conversation ID and its displayed messages locally. */
export function saveConversation(conversationId, messages) {
  if (!conversationId || !Array.isArray(messages)) {
    return false;
  }

  const existingRecents = readRecentConversationsFromStorage();
  try {
    window.localStorage.setItem(ACTIVE_CONVERSATION_KEY, conversationId);
    window.localStorage.setItem(
      getConversationKey(conversationId),
      JSON.stringify({ conversationId, messages }),
    );
    if (existingRecents === null) {
      return false;
    }

    const nextRecents = upsertRecentConversation(
      existingRecents,
      conversationId,
      messages,
    );
    window.localStorage.setItem(
      RECENT_CONVERSATIONS_KEY,
      JSON.stringify(nextRecents),
    );
    const retainedIds = new Set(
      nextRecents.map((conversation) => conversation.conversationId),
    );
    for (const conversation of existingRecents) {
      if (!retainedIds.has(conversation.conversationId)) {
        window.localStorage.removeItem(
          getConversationKey(conversation.conversationId),
        );
      }
    }
    return true;
  } catch (error) {
    logStorageFailure("write", error);
    return false;
  }
}

/** Clear only the active selection so saved chats remain available in Recents. */
export function clearActiveConversation() {
  try {
    window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    return true;
  } catch (error) {
    logStorageFailure("clear-active", error);
    return false;
  }
}

/** Delete a saved conversation and its sidebar entry from local storage. */
export function clearConversation(conversationId = null) {
  const existingRecents = readRecentConversationsFromStorage();
  try {
    const activeConversationId = window.localStorage.getItem(
      ACTIVE_CONVERSATION_KEY,
    );
    const conversationToClear = conversationId || activeConversationId;
    if (conversationToClear) {
      window.localStorage.removeItem(getConversationKey(conversationToClear));
    }
    if (
      !conversationId ||
      activeConversationId === conversationId
    ) {
      window.localStorage.removeItem(ACTIVE_CONVERSATION_KEY);
    }
    if (conversationToClear && existingRecents !== null) {
      const nextRecents = existingRecents.filter(
        (conversation) =>
          conversation.conversationId !== conversationToClear,
      );
      window.localStorage.setItem(
        RECENT_CONVERSATIONS_KEY,
        JSON.stringify(nextRecents),
      );
    }
    return true;
  } catch (error) {
    logStorageFailure("clear", error);
    return false;
  }
}
