import { useRef, useState } from "react";

export function DocumentPanel({ documents, onAttach, onRemove, disabled, error }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  function attachFiles(files) {
    for (const file of Array.from(files || [])) {
      onAttach(file);
    }
  }

  return (
    <section
      className={`document-panel${dragging ? " document-panel--dragging" : ""}`}
      aria-label="Supporting documents"
      onDragEnter={(event) => {
        event.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        setDragging(false);
        attachFiles(event.dataTransfer.files);
      }}
    >
      <input
        accept=".pdf,.docx,.txt,.md"
        hidden
        onChange={(event) => {
          attachFiles(event.target.files);
          event.target.value = "";
        }}
        ref={inputRef}
        type="file"
        multiple
      />
      <button
        aria-label="Attach document"
        className="button button--secondary document-panel__attach"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        title="Attach document"
        type="button"
      >
        <svg
          aria-hidden="true"
          className="document-panel__clip"
          viewBox="0 0 24 24"
        >
          <path d="M9.5 7.5v7.25a2.75 2.75 0 0 0 5.5 0V6a4.25 4.25 0 0 0-8.5 0v10a5.75 5.75 0 0 0 11.5 0V7" />
        </svg>
      </button>
      <small className="document-panel__limits">PDF, DOCX, TXT, or MD · 10 MB maximum · 5 per conversation</small>
      {error ? <p className="document-panel__error" role="alert">{error}</p> : null}
      <ul className="document-chips">
        {documents.map((document) => (
          <li className={`document-chip document-chip--${document.status || "ready"}`} key={document.document_id}>
            <span>{document.name || document.filename || document.document_id}</span>
            {document.status === "uploading" ? <small>Uploading</small> : null}
            {document.status === "failed" ? <small>{document.error}</small> : null}
            {document.status !== "uploading" ? (
              <button
                aria-label={`Remove ${document.name || document.filename || "document"}`}
                onClick={() => onRemove(document.document_id)}
                type="button"
              >
                Remove
              </button>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  );
}
