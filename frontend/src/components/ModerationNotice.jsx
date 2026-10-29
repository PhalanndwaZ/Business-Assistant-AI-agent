const GENERIC_REDACTION_NOTICE =
  "Some content was withheld because of your access level.";

export function getRedactionNotice(moderation) {
  if (moderation?.status !== "redacted") {
    return null;
  }
  return typeof moderation.notice === "string" && moderation.notice.trim()
    ? moderation.notice
    : GENERIC_REDACTION_NOTICE;
}

/** Show only the notice supplied for a redacted answer. */
export function ModerationNotice({ moderation }) {
  const notice = getRedactionNotice(moderation);
  if (!notice) {
    return null;
  }

  return (
    <p className="moderation-notice" role="note">
      {notice}
    </p>
  );
}
