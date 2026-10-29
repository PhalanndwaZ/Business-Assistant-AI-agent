/** Show a normalized error and let the user retry its original question. */
export function ErrorBanner({
  message,
  onRetry,
  retryAfterSeconds = 0,
}) {
  const retryDisabled = retryAfterSeconds > 0;

  return (
    <div className="message-error" role="alert">
      <p className="message-error__text">{message}</p>
      {onRetry ? (
        <button
          className="button button--secondary message-error__retry"
          onClick={onRetry}
          disabled={retryDisabled}
          type="button"
        >
          {retryDisabled ? `Retry in ${retryAfterSeconds}s` : "Retry"}
        </button>
      ) : null}
    </div>
  );
}
