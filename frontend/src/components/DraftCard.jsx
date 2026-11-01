import { useState } from "react";

export function DraftCard({ draft, onSave }) {
  const [body, setBody] = useState(draft.body || "");
  const [subject, setSubject] = useState(draft.subject || "");

  async function copyDraft() {
    await navigator.clipboard.writeText(`${subject}\n\n${body}`);
  }

  return (
    <article className="draft-card">
      <div className="draft-card__heading">
        <strong>{draft.purpose || "Message draft"}</strong>
        <span>{draft.status}</span>
      </div>
      <label>
        Subject
        <input value={subject} onChange={(event) => setSubject(event.target.value)} />
      </label>
      <label>
        Message
        <textarea value={body} onChange={(event) => setBody(event.target.value)} />
      </label>
      {Array.isArray(draft.warnings) && draft.warnings.length > 0 ? (
        <ul className="draft-card__warnings">
          {draft.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
      ) : null}
      {draft.facts_used !== undefined && draft.facts_used !== null ? (
        <details className="draft-card__facts">
          <summary>Facts used</summary>
          <pre>{JSON.stringify(draft.facts_used, null, 2)}</pre>
        </details>
      ) : null}
      <div className="draft-card__actions">
        <button className="button button--secondary" onClick={copyDraft} type="button">Copy</button>
        <button className="button button--secondary" onClick={() => onSave(draft.draft_id, { subject, body })} type="button">Save edits</button>
        <button className="button button--secondary" onClick={() => onSave(draft.draft_id, { status: "approved" })} type="button">Mark approved</button>
        <button className="button button--secondary" onClick={() => onSave(draft.draft_id, { status: "discarded" })} type="button">Discard</button>
      </div>
      <p className="draft-card__notice">Draft, not sent</p>
    </article>
  );
}
