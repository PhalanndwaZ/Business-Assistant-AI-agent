import { useCallback, useEffect, useRef, useState } from "react";

import { askQuestion } from "../api/client.js";
import { ApiRequestError, normalizeApiError } from "../api/errors.js";
import {
  clearActiveConversation,
  loadConversation,
  loadConversationById,
  loadRecentConversations,
  saveConversation,
  upsertRecentConversation,
} from "../storage/conversationStore.js";

/** Create a message with an identifier that remains local to this browser. */
function createMessage(role, content, response = null) {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    ...(response ? { response } : {}),
  };
}

/** Manage chat messages, backend conversation identity, and request lifecycle. */
export function useConversation() {
  const [initialConversation] = useState(loadConversation);
  const [recentConversations, setRecentConversations] = useState(
    loadRecentConversations,
  );
  const [messages, setMessages] = useState(
    initialConversation?.messages || [],
  );
  const [conversationId, setConversationId] = useState(
    initialConversation?.conversationId || null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const activeRequestRef = useRef(null);
  const requestGenerationRef = useRef(0);

  /** Persist messages and keep the local Recents list updated in memory. */
  const persistConversation = useCallback(function persistSavedConversation(
    savedConversationId,
    savedMessages,
  ) {
    saveConversation(savedConversationId, savedMessages);
    setRecentConversations((currentConversations) =>
      upsertRecentConversation(
        currentConversations,
        savedConversationId,
        savedMessages,
      ),
    );
  }, []);

  /** Submit a question, optionally reusing the existing user message on retry. */
  const submitQuestion = useCallback(
    async function submitQuestionRequest(question, isRetry = false) {
      const normalizedQuestion =
        typeof question === "string" ? question.trim() : "";
      if (!normalizedQuestion || activeRequestRef.current) {
        return;
      }

      const requestMessages = isRetry
        ? messages
        : [...messages, createMessage("user", normalizedQuestion)];
      const controller = new AbortController();
      const requestGeneration = requestGenerationRef.current;
      activeRequestRef.current = controller;
      setMessages(requestMessages);
      setError(null);
      setLoading(true);
      if (conversationId) {
        persistConversation(conversationId, requestMessages);
      }

      try {
        const response = await askQuestion({
          question: normalizedQuestion,
          conversationId,
          signal: controller.signal,
        });
        if (requestGeneration !== requestGenerationRef.current) {
          return;
        }

        const nextConversationId = response.conversation_id;
        const completedMessages = [
          ...requestMessages,
          createMessage("assistant", response.answer, response),
        ];
        setConversationId(nextConversationId);
        setMessages(completedMessages);
        persistConversation(nextConversationId, completedMessages);
      } catch (requestError) {
        if (requestGeneration !== requestGenerationRef.current) {
          return;
        }
        const safeError =
          requestError instanceof ApiRequestError
            ? requestError
            : normalizeApiError({
                cause: requestError,
                invalidResponse: true,
              });
        setError({
          kind: safeError.kind,
          message: safeError.message,
          question: normalizedQuestion,
        });
      } finally {
        if (activeRequestRef.current === controller) {
          activeRequestRef.current = null;
        }
        if (requestGeneration === requestGenerationRef.current) {
          setLoading(false);
        }
      }
    },
    [conversationId, messages, persistConversation],
  );

  /** Send a new user question unless another request is still in flight. */
  const send = useCallback(
    function sendQuestion(question) {
      return submitQuestion(question);
    },
    [submitQuestion],
  );

  /** Retry the last failed question without adding a duplicate user message. */
  const retry = useCallback(
    function retryQuestion() {
      if (!error?.question) {
        return;
      }
      return submitQuestion(error.question, true);
    },
    [error, submitQuestion],
  );

  /** Abort the active request and let the hook record its cancellation state. */
  const cancel = useCallback(function cancelRequest() {
    activeRequestRef.current?.abort();
  }, []);

  /** Start a blank chat while retaining saved conversations in Recents. */
  const reset = useCallback(
    function resetConversation() {
      requestGenerationRef.current += 1;
      activeRequestRef.current?.abort();
      activeRequestRef.current = null;
      clearActiveConversation();
      setConversationId(null);
      setMessages([]);
      setError(null);
      setLoading(false);
    },
    [],
  );

  /** Switch to a saved conversation without sharing history with other chats. */
  const selectConversation = useCallback(
    function selectSavedConversation(selectedConversationId) {
      if (
        !selectedConversationId ||
        selectedConversationId === conversationId ||
        activeRequestRef.current
      ) {
        return false;
      }

      const conversation = loadConversationById(selectedConversationId);
      if (!conversation) {
        setError({
          kind: "storage",
          message: "That saved chat is no longer available in this browser.",
          question: null,
        });
        return false;
      }

      requestGenerationRef.current += 1;
      activeRequestRef.current?.abort();
      activeRequestRef.current = null;
      setConversationId(conversation.conversationId);
      setMessages(conversation.messages);
      setError(null);
      setLoading(false);
      return true;
    },
    [conversationId],
  );

  useEffect(function cancelRequestOnUnmount() {
    /** Abort pending work and invalidate its eventual response on unmount. */
    function abortPendingRequest() {
      requestGenerationRef.current += 1;
      activeRequestRef.current?.abort();
    }

    return abortPendingRequest;
  }, []);

  return {
    messages,
    conversationId,
    recentConversations,
    loading,
    error,
    send,
    retry,
    cancel,
    reset,
    selectConversation,
  };
}
