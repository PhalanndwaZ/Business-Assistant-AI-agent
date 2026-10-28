import { AssistantMessage } from "./AssistantMessage.jsx";
import { ErrorBanner } from "./ErrorBanner.jsx";
import { LoadingIndicator } from "./LoadingIndicator.jsx";
import { UserMessage } from "./UserMessage.jsx";
import { useElapsedTime } from "../hooks/useElapsedTime.js";

/** Display chat messages with live announcements and separate request errors. */
export function MessageList({
  messages,
  loading,
  error,
  onCancel,
  onRetry,
}) {
  const elapsedSeconds = useElapsedTime(loading);
  const messageItems = [];
  for (const message of messages) {
    messageItems.push(
      <li
        className={`message-row message-row--${message.role}`}
        key={message.id}
      >
        {message.role === "user" ? (
          <UserMessage content={message.content} />
        ) : (
          <AssistantMessage
            content={message.content}
            response={message.response}
          />
        )}
      </li>,
    );
  }

  return (
    <section className="message-list" aria-label="Conversation">
      <ol aria-live="polite" aria-relevant="additions text">
        {messageItems}
      </ol>
      {loading ? (
        <LoadingIndicator
          elapsedSeconds={elapsedSeconds}
          onCancel={onCancel}
        />
      ) : null}
      {error?.kind === "cancelled" ? (
        <p className="message-cancelled" role="status">
          Cancelled
        </p>
      ) : null}
      {error && error.kind !== "cancelled" ? (
        <ErrorBanner
          message={error.message}
          onRetry={error.question ? onRetry : null}
        />
      ) : null}
    </section>
  );
}
