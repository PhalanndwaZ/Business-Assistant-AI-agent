import { createContext, useCallback, useEffect, useMemo, useState } from "react";

import { getMe, login as loginRequest } from "../api/authApi.js";
import {
  clearAuthSession,
  clearPendingQuestion as clearSavedPendingQuestion,
  loadAuthToken,
  loadAuthUser,
  loadPendingQuestion,
  savePendingQuestion,
  saveAuthSession,
} from "./authStore.js";
import {
  clearLegacyConversationData,
  clearUserConversations,
} from "../storage/conversationStore.js";

export const AuthContext = createContext(null);

/** Provide the current user session and auth actions to the React tree. */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [sessionExpired, setSessionExpired] = useState(false);
  const [pendingQuestion, setPendingQuestion] = useState(loadPendingQuestion);

  /** Subscribe to session invalidation raised by authenticated API calls. */
  useEffect(function listenForExpiredSession() {
    /** Clear the visible identity after the API client rejects a token. */
    function handleSessionExpired(event) {
      const expiredUser = user || loadAuthUser();
      const question = event.detail?.question;
      const userId = event.detail?.userId || expiredUser?.user_id;
      if (
        typeof question === "string" &&
        question.trim() &&
        typeof userId === "string" &&
        userId
      ) {
        const pending = { question: question.trim(), userId };
        savePendingQuestion(pending.question, pending.userId);
        setPendingQuestion(pending);
      }
      if (expiredUser?.user_id) {
        clearUserConversations(expiredUser.user_id);
      }
      clearAuthSession();
      setUser(null);
      setSessionExpired(true);
      setIsLoading(false);
    }

    window.addEventListener(
      "business-analyst-ai:session-expired",
      handleSessionExpired,
    );
    return function removeSessionExpiredListener() {
      window.removeEventListener(
        "business-analyst-ai:session-expired",
        handleSessionExpired,
      );
    };
  }, [user]);

  /** Restore a saved session only after validating it with the API. */
  useEffect(function restoreSavedSession() {
    const accessToken = loadAuthToken();
    const storedUser = loadAuthUser();
    clearLegacyConversationData();
    if (!accessToken) {
      setIsLoading(false);
      return undefined;
    }

    const controller = new AbortController();
    let active = true;

    /** Verify a saved token with the backend before exposing its user. */
    async function verifySavedSession() {
      try {
        const currentUser = await getMe({ signal: controller.signal });
        if (active) {
          const savedPendingQuestion = loadPendingQuestion();
          if (
            storedUser?.user_id &&
            storedUser.user_id !== currentUser.user_id
          ) {
            clearUserConversations(storedUser.user_id);
          }
          if (
            savedPendingQuestion &&
            savedPendingQuestion.userId !== currentUser.user_id
          ) {
            clearSavedPendingQuestion();
            setPendingQuestion(null);
          } else {
            setPendingQuestion(savedPendingQuestion);
          }
          saveAuthSession(accessToken, currentUser);
          setUser(currentUser);
        }
      } catch (error) {
        if (active && error?.kind !== "cancelled") {
          if (storedUser?.user_id) {
            clearUserConversations(storedUser.user_id);
          }
          clearAuthSession();
          setUser(null);
          if (error?.status === 401) {
            setSessionExpired(true);
          }
        }
      } finally {
        if (active) {
          setIsLoading(false);
        }
      }
    }

    verifySavedSession();
    return function cancelSessionRestore() {
      active = false;
      controller.abort();
    };
  }, []);

  /** Sign in, verify the returned bearer token, and store the profile. */
  const signIn = useCallback(async function signInUser(username, password) {
    const previousUser = user || loadAuthUser();
    try {
      const loginResponse = await loginRequest(username, password);
      saveAuthSession(loginResponse.access_token);
      const currentUser = await getMe();
      const savedPendingQuestion = loadPendingQuestion();
      if (
        previousUser?.user_id &&
        previousUser.user_id !== currentUser.user_id
      ) {
        clearUserConversations(previousUser.user_id);
      }
      if (
        savedPendingQuestion &&
        savedPendingQuestion.userId !== currentUser.user_id
      ) {
        clearSavedPendingQuestion();
        setPendingQuestion(null);
      } else {
        setPendingQuestion(savedPendingQuestion);
      }
      saveAuthSession(loginResponse.access_token, currentUser);
      setUser(currentUser);
      setSessionExpired(false);
      return currentUser;
    } catch (error) {
      if (previousUser?.user_id) {
        clearUserConversations(previousUser.user_id);
      }
      clearAuthSession();
      setUser(null);
      throw error;
    }
  }, [user]);

  /** End the session and remove its token, profile, and saved chat data. */
  const signOut = useCallback(function signOutUser() {
    if (user?.user_id) {
      clearUserConversations(user.user_id);
    }
    clearSavedPendingQuestion();
    setPendingQuestion(null);
    clearAuthSession();
    setUser(null);
    setSessionExpired(false);
  }, [user]);

  /** Clear the expired-session notice before a new login attempt. */
  const clearSessionExpired = useCallback(function clearExpiredNotice() {
    setSessionExpired(false);
  }, []);

  /** Clear the saved question after the user resends or dismisses it. */
  const clearPendingQuestion = useCallback(
    function clearSavedQuestion() {
      clearSavedPendingQuestion();
      setPendingQuestion(null);
    },
    [],
  );

  /** Memoize the auth state and actions shared with descendant components. */
  const contextValue = useMemo(
    function createAuthContextValue() {
      return {
        user,
        isLoading,
        isAuthenticated: user !== null,
        sessionExpired,
        pendingQuestion,
        signIn,
        signOut,
        clearSessionExpired,
        clearPendingQuestion,
      };
    },
    [
      user,
      isLoading,
      sessionExpired,
      pendingQuestion,
      signIn,
      signOut,
      clearSessionExpired,
      clearPendingQuestion,
    ],
  );

  return (
    <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>
  );
}
