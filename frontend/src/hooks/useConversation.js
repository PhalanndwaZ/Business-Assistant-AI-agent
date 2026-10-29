import { useCallback, useEffect, useRef, useState } from "react";

import { askQuestion } from "../api/client.js";
import { ApiRequestError, normalizeApiError } from "../api/errors.js";
import {
  clearActiveConversation,
  clearConversation,
  loadConversation,
  loadConversationById,
  loadRecentConversations,
  saveConversation,
  upsertRecentConversation,
} from "../storage/conversationStore.js";

const CONVERSATION_NOT_FOUND_NOTICE =
  "That conversation is no longer available, so a new one was started.";

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
export function useConversation(userId) {
  const [initialConversation] = useState(() => loadConversation(userId));
  const [recentConversations, setRecentConversations] = useState(
    () => loadRecentConversations(userId),
  );
  const [messages, setMessages] = useState(
    initialConversation?.messages || [],
  );
  const [conversationId, setConversationId] = useState(
    initialConversation?.conversationId || null,
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [sessionNotice, setSessionNotice] = useState(null);
  const [retryAfterSeconds, setRetryAfterSeconds] = useState(0);
  const activeRequestRef = useRef(null);
  const requestGenerationRef = useRef(0);

  useEffect(
    function countDownRateLimit() {
      if (retryAfterSeconds <= 0) {
        return undefined;
      }
      const timeoutId = setTimeout(
        () => setRetryAfterSeconds((seconds) => Math.max(0, seconds - 1)),
        1000,
      );
      return () => clearTimeout(timeoutId);
    },
    [retryAfterSeconds],
  );

  /** Persist messages and keep the local Recents list updated in memory. */
  const persistConversation = useCallback(function persistSavedConversation(
    savedConversationId,
    savedMessages,
  ) {
    saveConversation(userId, savedConversationId, savedMessages);
    setRecentConversations((currentConversations) =>
      upsertRecentConversation(
        currentConversations,
        savedConversationId,
        savedMessages,
      ),
    );
  }, [userId]);

  /** Submit a question, optionally reusing the existing user message on retry. */
  const submitQuestion = useCallback(
    async function submitQuestionRequest(question, isRetry = false) {
      const normalizedQuestion =
        typeof question === "string" ? question.trim() : "";
      if (
        !normalizedQuestion ||
        activeRequestRef.current ||
        retryAfterSeconds > 0
      ) {
        return;
      }

      let requestMessages = isRetry
        ? messages
        : [...messages, createMessage("user", normalizedQuestion)];
      const controller = new AbortController();
      const requestGeneration = requestGenerationRef.current;
      activeRequestRef.current = controller;
      setMessages(requestMessages);
      setError(null);
      setSessionNotice(null);
      setRetryAfterSeconds(0);
      setLoading(true);
      if (conversationId) {
        persistConversation(conversationId, requestMessages);
      }

      let conversationWasReset = false;
      try {
        let response;
        try {
          response = await askQuestion({
            question: normalizedQuestion,
            conversationId,
            signal: controller.signal,
          });
        } catch (requestError) {
          if (
            !(requestError instanceof ApiRequestError) ||
            requestError.status !== 404 ||
            !conversationId
          ) {
            throw requestError;
          }
          if (requestGeneration !== requestGenerationRef.current) {
            return;
          }

          clearConversation(userId, conversationId);
          setRecentConversations(loadRecentConversations(userId));
          setConversationId(null);
          requestMessages = [createMessage("user", normalizedQuestion)];
          setMessages(requestMessages);
          conversationWasReset = true;
          response = await askQuestion({
            question: normalizedQuestion,
            conversationId: null,
            signal: controller.signal,
          });
        }
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
        setSessionNotice(
          conversationWasReset ? CONVERSATION_NOT_FOUND_NOTICE : null,
        );
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
        const nextRetryAfterSeconds =
          safeError.status === 429 && safeError.retryAfter !== null
            ? Math.ceil(safeError.retryAfter)
            : 0;
        setRetryAfterSeconds(nextRetryAfterSeconds);
        setError({
          kind: safeError.kind,
          message:
            safeError.status === 404 &&
            (!conversationId || conversationWasReset)
              ? "Something went wrong. Please try again."
              : safeError.message,
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
    [conversationId, messages, persistConversation, retryAfterSeconds, userId],
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
      if (!error?.question || retryAfterSeconds > 0) {
        return;
      }
      return submitQuestion(error.question, true);
    },
    [error, retryAfterSeconds, submitQuestion],
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
      clearActiveConversation(userId);
      setConversationId(null);
      setMessages([]);
      setError(null);
      setSessionNotice(null);
      setRetryAfterSeconds(0);
      setLoading(false);
    },
    [userId],
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

      const conversation = loadConversationById(
        userId,
        selectedConversationId,
      );
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
      setSessionNotice(null);
      setRetryAfterSeconds(0);
      setLoading(false);
      return true;
    },
    [conversationId, userId],
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
    sessionNotice,
    retryAfterSeconds,
    send,
    retry,
    cancel,
    reset,
    selectConversation,
  };
}
