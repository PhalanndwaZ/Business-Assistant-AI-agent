/** Show a normalized error and let the user retry its original question. */
export function ErrorBanner({ message, onRetry }) {
  return (
    <div className="message-error" role="alert">
      <p className="message-error__text">{message}</p>
      {onRetry ? (
        <button
          className="button button--secondary message-error__retry"
          onClick={onRetry}
          type="button"
        >
          Retry
        </button>
      ) : null}
    </div>
  );
}
