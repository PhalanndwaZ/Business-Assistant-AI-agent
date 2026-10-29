/** Show a non-error session or conversation status with optional actions. */
export function SessionNotice({
  message,
  detail = null,
  actionLabel = null,
  onAction = null,
  actionDisabled = false,
  dismissLabel = null,
  onDismiss = null,
}) {
  return (
    <aside className="session-notice" role="status">
      <div className="session-notice__content">
        <p className="session-notice__message">{message}</p>
        {detail ? <p className="session-notice__detail">{detail}</p> : null}
      </div>
      {actionLabel && onAction ? (
        <button
          className="button button--secondary session-notice__action"
          onClick={onAction}
          disabled={actionDisabled}
          type="button"
        >
          {actionLabel}
        </button>
      ) : null}
      {dismissLabel && onDismiss ? (
        <button
          className="button button--secondary session-notice__dismiss"
          onClick={onDismiss}
          type="button"
        >
          {dismissLabel}
        </button>
      ) : null}
    </aside>
  );
}
