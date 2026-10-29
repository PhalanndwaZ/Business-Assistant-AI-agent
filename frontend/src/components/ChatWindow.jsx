import { useEffect, useRef, useState } from "react";

import { ExampleQuestions } from "./ExampleQuestions.jsx";
import { MessageList } from "./MessageList.jsx";
import { QuestionInput } from "./QuestionInput.jsx";
import { RecentConversations } from "./RecentConversations.jsx";
import { SessionNotice } from "./SessionNotice.jsx";
import { UserMenu } from "./UserMenu.jsx";
import { STARTER_QUESTIONS_BY_ROLE } from "../config.js";

/** Compose the conversation sidebar, message area, and question input. */
export function ChatWindow({
  messages,
  loading,
  error,
  sessionNotice,
  retryAfterSeconds,
  conversationId,
  recentConversations,
  send,
  cancel,
  retry,
  reset,
  selectConversation,
  user,
  onLogout,
  pendingQuestion,
  onClearPendingQuestion,
}) {
  const questionInputRef = useRef(null);
  const recentSidebarRef = useRef(null);
  const recentHeadingRef = useRef(null);
  const recentToggleRef = useRef(null);
  const recentSidebarWasOpenRef = useRef(false);
  const focusInputAfterCloseRef = useRef(false);
  const [recentSidebarOpen, setRecentSidebarOpen] = useState(false);
  const starterQuestions = STARTER_QUESTIONS_BY_ROLE[user.role] || [];
  const isAdminWithoutAuditView = user.role === "admin";

  useEffect(
    /** Return focus to the input after the current response finishes. */
    function focusInputAfterResponse() {
      if (!loading && !error) {
        questionInputRef.current?.focus();
      }
    },
    [loading, error],
  );

  useEffect(
    /** Move focus into the mobile drawer and restore it when the drawer closes. */
    function manageRecentSidebarFocus() {
      if (recentSidebarOpen) {
        recentHeadingRef.current?.focus();
      } else if (recentSidebarWasOpenRef.current) {
        const focusTarget = focusInputAfterCloseRef.current
          ? questionInputRef.current
          : recentToggleRef.current;
        focusTarget?.focus();
      }
      recentSidebarWasOpenRef.current = recentSidebarOpen;
    },
    [recentSidebarOpen],
  );

  useEffect(
    /** Close the mobile recent-chat drawer when Escape is pressed. */
    function closeRecentSidebarOnEscape() {
      if (!recentSidebarOpen) {
        return undefined;
      }

      function handleEscape(event) {
        if (event.key === "Escape") {
          focusInputAfterCloseRef.current = false;
          setRecentSidebarOpen(false);
        }
      }

      window.addEventListener("keydown", handleEscape);
      return function removeEscapeHandler() {
        window.removeEventListener("keydown", handleEscape);
      };
    },
    [recentSidebarOpen],
  );

  /** Switch chats and direct focus to the question input after selection. */
  function handleSelectConversation(selectedConversationId) {
    selectConversation(selectedConversationId);
    focusInputAfterCloseRef.current = true;
    setRecentSidebarOpen(false);
    if (!recentSidebarWasOpenRef.current) {
      questionInputRef.current?.focus();
    }
  }

  /** Start a blank chat without removing any saved conversation. */
  function handleNewConversation() {
    reset();
    focusInputAfterCloseRef.current = true;
    setRecentSidebarOpen(false);
    if (!recentSidebarWasOpenRef.current) {
      questionInputRef.current?.focus();
    }
  }

  /** Resend a question kept when this user's session expired. */
  function handleResendPendingQuestion() {
    if (!pendingQuestion) {
      return;
    }
    send(pendingQuestion);
    onClearPendingQuestion?.();
  }

  /** Keep keyboard focus inside the modal drawer while it is open. */
  function handleRecentSidebarKeyDown(event) {
    if (event.key === "Escape") {
      focusInputAfterCloseRef.current = false;
      setRecentSidebarOpen(false);
      return;
    }
    if (event.key !== "Tab") {
      return;
    }

    const focusableItems = recentSidebarRef.current?.querySelectorAll(
      "button:not(:disabled)",
    );
    if (!focusableItems?.length) {
      event.preventDefault();
      recentHeadingRef.current?.focus();
      return;
    }

    const firstItem = focusableItems[0];
    const lastItem = focusableItems[focusableItems.length - 1];
    if (
      event.shiftKey &&
      (document.activeElement === firstItem ||
        document.activeElement === recentHeadingRef.current)
    ) {
      event.preventDefault();
      lastItem.focus();
    } else if (
      !event.shiftKey &&
      (document.activeElement === lastItem ||
        document.activeElement === recentHeadingRef.current)
    ) {
      event.preventDefault();
      firstItem.focus();
    }
  }

  return (
    <div className="app-shell">
      <RecentConversations
        activeConversationId={conversationId}
        conversations={recentConversations}
        disabled={loading}
        headingRef={recentHeadingRef}
        isOpen={recentSidebarOpen}
        onClose={() => {
          focusInputAfterCloseRef.current = false;
          setRecentSidebarOpen(false);
        }}
        onKeyDown={handleRecentSidebarKeyDown}
        onNewConversation={handleNewConversation}
        onSelect={handleSelectConversation}
        sidebarRef={recentSidebarRef}
      />
      <div className="app-workspace">
        <header className="app-header">
          <div className="app-header__inner">
            <div className="app-header__actions">
              <UserMenu user={user} onLogout={onLogout} />
            </div>
          </div>
        </header>

        <div className="mobile-history-toolbar">
          <button
            aria-controls="recent-conversations"
            aria-expanded={recentSidebarOpen}
            className="button button--secondary mobile-history-toggle"
            onClick={() => {
              focusInputAfterCloseRef.current = false;
              setRecentSidebarOpen((isOpen) => !isOpen);
            }}
            ref={recentToggleRef}
            type="button"
          >
            Chats
          </button>
        </div>

        <main className="chat-main">
          <div className="chat-content">
            {messages.length === 0 && !loading ? (
              <section className="empty-state" aria-labelledby="welcome-title">
                <p className="empty-state__eyebrow">
                  {isAdminWithoutAuditView
                    ? "Administrator account"
                    : "Ask a business question"}
                </p>
                <h2 id="welcome-title">
                  {isAdminWithoutAuditView
                    ? "No business data available"
                    : "Answers grounded in your data"}
                </h2>
                <p>
                  {isAdminWithoutAuditView
                    ? "This account has no business data."
                    : "Ask about business results or supporting documents. Answers are checked against the available evidence."}
                </p>
                {starterQuestions.length > 0 ? (
                  <ExampleQuestions
                    questions={starterQuestions}
                    onSelect={send}
                    disabled={loading}
                  />
                ) : null}
              </section>
            ) : null}
            {sessionNotice ? <SessionNotice message={sessionNotice} /> : null}
            {pendingQuestion ? (
              <SessionNotice
                message="Your unsent question was saved when your session expired."
                detail={pendingQuestion}
                actionLabel="Resend question"
                onAction={handleResendPendingQuestion}
                actionDisabled={loading || retryAfterSeconds > 0}
                dismissLabel="Discard"
                onDismiss={onClearPendingQuestion}
              />
            ) : null}
            <MessageList
              messages={messages}
              loading={loading}
              error={error}
              retryAfterSeconds={retryAfterSeconds}
              onCancel={cancel}
              onRetry={retry}
            />
          </div>
        </main>

        <div className="input-dock">
          <QuestionInput
            disabled={loading || retryAfterSeconds > 0}
            inputRef={questionInputRef}
            onSend={send}
          />
        </div>
      </div>
    </div>
  );
}
