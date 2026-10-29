import { useState } from "react";

import { SessionNotice } from "./SessionNotice.jsx";
import { DEMO_USERNAMES } from "../config.js";

/** Render the username/password form and optional demo-account list. */
export function LoginView({
  onLogin,
  showDemoAccounts = false,
  sessionExpired = false,
  hasPendingQuestion = false,
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errorMessage, setErrorMessage] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  /** Update the username draft. */
  function handleUsernameChange(event) {
    setUsername(event.target.value);
  }

  /** Update the password draft. */
  function handlePasswordChange(event) {
    setPassword(event.target.value);
  }

  /** Submit credentials and show only a safe, normalized error message. */
  async function handleSubmit(event) {
    event.preventDefault();
    if (isSubmitting) {
      return;
    }
    setErrorMessage("");
    setIsSubmitting(true);
    try {
      await onLogin(username.trim(), password);
    } catch (error) {
      setErrorMessage(
        typeof error?.message === "string"
          ? error.message
          : "Something went wrong. Please try again.",
      );
    } finally {
      setIsSubmitting(false);
    }
  }

  /** Render one demo username without displaying credentials. */
  function renderDemoUsername(demoUsername) {
    return <li key={demoUsername}>{demoUsername}</li>;
  }

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <p className="login-card__eyebrow">Business Analyst AI</p>
        <h1 id="login-title">Sign in</h1>
        <p className="login-card__intro">
          Sign in to continue to your business analysis workspace.
        </p>
        {sessionExpired || hasPendingQuestion ? (
          <SessionNotice
            message={
              sessionExpired
                ? "Your session has expired. Please log in again."
                : "Sign in to continue with your saved question."
            }
            detail={
              hasPendingQuestion
                ? "Your unsent question is saved. After signing in, you can choose to resend it."
                : null
            }
          />
        ) : null}
        <form className="login-form" onSubmit={handleSubmit}>
          <label htmlFor="login-username">Username</label>
          <input
            autoComplete="username"
            id="login-username"
            name="username"
            onChange={handleUsernameChange}
            required
            value={username}
          />
          <label htmlFor="login-password">Password</label>
          <input
            autoComplete="current-password"
            id="login-password"
            name="password"
            onChange={handlePasswordChange}
            required
            type="password"
            value={password}
          />
          {errorMessage ? (
            <p className="login-form__error" role="alert">
              {errorMessage}
            </p>
          ) : null}
          <button
            className="button button--primary login-form__submit"
            disabled={isSubmitting || !username.trim() || !password}
            type="submit"
          >
            {isSubmitting ? "Signing in..." : "Sign in"}
          </button>
        </form>
        {showDemoAccounts ? (
          <aside className="demo-accounts" aria-labelledby="demo-accounts-title">
            <h2 id="demo-accounts-title">Demo accounts</h2>
            <ul>
              {DEMO_USERNAMES.map(renderDemoUsername)}
            </ul>
          </aside>
        ) : null}
      </section>
    </main>
  );
}
