import { useEffect, useRef, useState } from "react";

import { ExampleQuestions } from "./ExampleQuestions.jsx";
import { MessageList } from "./MessageList.jsx";
import { QuestionInput } from "./QuestionInput.jsx";
import { RecentConversations } from "./RecentConversations.jsx";
import { SessionNotice } from "./SessionNotice.jsx";
import { UserMenu } from "./UserMenu.jsx";
import { STARTER_QUESTIONS_BY_ROLE } from "../config.js";
import { DocumentsPanel } from "./DocumentsPanel.jsx";
import { AdminUsersPanel } from "./AdminUsersPanel.jsx";
import { ManagerOverviewPanel } from "./ManagerOverviewPanel.jsx";

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
  darkMode,
  onToggleDarkMode,
  pendingQuestion,
  onClearPendingQuestion,
  documents = [],
  onAttachDocument,
  onRemoveDocument,
  documentError,
}) {
  const questionInputRef = useRef(null);
  const recentSidebarRef = useRef(null);
  const recentHeadingRef = useRef(null);
  const recentToggleRef = useRef(null);
  const chatMainRef = useRef(null);
  const recentSidebarWasOpenRef = useRef(false);
  const focusInputAfterCloseRef = useRef(false);
  const requestStartedRef = useRef(false);
  const [recentSidebarOpen, setRecentSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const starterQuestions = STARTER_QUESTIONS_BY_ROLE[user.role] || [];
  const isAdmin = user.role === "admin";
  const isManager = user.role === "manager";
  const firstName = user.name?.trim().split(/\s+/)[0] || "there";

  useEffect(
    /** Return focus to the input after the current response finishes. */
    function focusInputAfterResponse() {
      if (loading) {
        requestStartedRef.current = true;
        return;
      }
      if (requestStartedRef.current) {
        requestStartedRef.current = false;
        if (!error) {
          questionInputRef.current?.focus();
        }
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

  /** Return to the top of the current workspace and focus its composer. */
  function handleFocusWorkspace() {
    focusInputAfterCloseRef.current = true;
    setRecentSidebarOpen(false);
    chatMainRef.current?.scrollTo({ top: 0, behavior: "smooth" });
    if (!recentSidebarWasOpenRef.current) {
      questionInputRef.current?.focus();
    }
  }

  /** Resend a question kept when this user's session expired. */
  function handleResendPendingQuestion() {
    if (!pendingQuestion) {
      return;
    }
    send(pendingQuestion, readyDocumentIds);
    onClearPendingQuestion?.();
  }

  const readyDocumentIds = documents
    .filter((document) => document.status !== "uploading" && document.status !== "failed" && document.document_id && !document.document_id.startsWith("pending-"))
    .map((document) => document.document_id);

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

    const focusableItems = [
      ...(recentSidebarRef.current?.querySelectorAll("button:not(:disabled)") ||
        []),
    ].filter((item) => item.getClientRects().length > 0);
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
    <div
      className={
        isAdmin
          ? "app-shell app-shell--admin"
          : sidebarCollapsed
            ? "app-shell app-shell--sidebar-collapsed"
            : "app-shell"
      }
    >
      {!isAdmin ? (
        <RecentConversations
          activeConversationId={conversationId}
          conversations={recentConversations}
          disabled={loading}
          headingRef={recentHeadingRef}
          isCollapsed={sidebarCollapsed}
          isOpen={recentSidebarOpen}
          user={user}
          darkMode={darkMode}
          onClose={() => {
            focusInputAfterCloseRef.current = false;
            setRecentSidebarOpen(false);
          }}
          onFocusWorkspace={handleFocusWorkspace}
          onKeyDown={handleRecentSidebarKeyDown}
          onNewConversation={handleNewConversation}
          onLogout={onLogout}
          onSelect={handleSelectConversation}
          onToggleCollapsed={() => setSidebarCollapsed((collapsed) => !collapsed)}
          onToggleDarkMode={onToggleDarkMode}
          sidebarRef={recentSidebarRef}
        />
      ) : null}
      <div className="app-workspace">
        <header className="app-header">
          <div className="app-header__inner">
            <div className="app-header__identity">
              <span className="app-header__mark" aria-hidden="true">
                BA
              </span>
              <div>
                <p className="app-header__product">Business Analyst AI</p>
                <p className="app-header__workspace">Your analysis workspace</p>
              </div>
            </div>
            {isAdmin ? (
              <div className="app-header__actions">
                <button
                  aria-label={
                    darkMode ? "Switch to light mode" : "Switch to dark mode"
                  }
                  aria-pressed={darkMode}
                  className="button button--secondary"
                  onClick={onToggleDarkMode}
                  type="button"
                >
                  {darkMode ? "Light mode" : "Dark mode"}
                </button>
                <UserMenu user={user} onLogout={onLogout} />
              </div>
            ) : null}
          </div>
        </header>

        {!isAdmin ? (
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
        ) : null}

        <main className="chat-main" ref={chatMainRef}>
          {isAdmin ? (
            <AdminUsersPanel />
          ) : (
            <div className="chat-content">
              {isManager ? <ManagerOverviewPanel /> : null}
              {messages.length === 0 && !loading ? (
                <section className="empty-state" aria-labelledby="welcome-title">
                  <p className="empty-state__eyebrow">
                    Good {getGreeting()}, {firstName}
                  </p>
                  <h2 id="welcome-title">Answers grounded in your data</h2>
                  <p>
                    Explore business results and supporting documents. Every
                    answer is checked against the available evidence.
                  </p>
                  {starterQuestions.length > 0 ? (
                    <div className="starter-prompts">
                      <div className="starter-prompts__heading">
                        <h3>Try asking</h3>
                        <span>Pick a prompt to get started</span>
                      </div>
                      <ExampleQuestions
                        questions={starterQuestions}
                        onSelect={send}
                        disabled={loading}
                      />
                    </div>
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
              {documents.length > 0 ? (
                <DocumentsPanel
                  disabled={loading}
                  documents={documents}
                  onRemove={onRemoveDocument}
                />
              ) : null}
            </div>
          )}
        </main>

        {!isAdmin ? (
          <div className="input-dock">
            <QuestionInput
              disabled={loading || retryAfterSeconds > 0}
              inputRef={questionInputRef}
              documents={documents}
              documentError={documentError}
              onAttachDocument={onAttachDocument}
              onRemoveDocument={onRemoveDocument}
              onSend={(question) => send(question, readyDocumentIds)}
            />
          </div>
        ) : null}
      </div>
    </div>
  );
}

/** Match the welcome message to the user's local time. */
function getGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) {
    return "morning";
  }
  if (hour < 18) {
    return "afternoon";
  }
  return "evening";
}
