/** Show request elapsed time and expose an explicit cancellation control. */
export function LoadingIndicator({ elapsedSeconds, onCancel }) {
  return (
    <div className="loading-indicator" role="status" aria-live="polite">
      <span>Analysing... {elapsedSeconds}s</span>
      <button
        className="button button--secondary"
        onClick={onCancel}
        type="button"
      >
        Cancel
      </button>
    </div>
  );
}
