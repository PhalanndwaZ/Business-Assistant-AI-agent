export function DocumentsPanel({ documents, onRemove, disabled }) {
  const visibleDocuments = documents.filter(
    (document) => document.document_id && !document.document_id.startsWith("pending-"),
  );

  return (
    <section className="documents-panel" aria-labelledby="documents-panel-heading">
      <h2 id="documents-panel-heading">Documents</h2>
      {visibleDocuments.length > 0 ? (
        <ul>
          {visibleDocuments.map((document) => (
            <li key={document.document_id}>
              <span>
                {document.name || document.filename || "Document"}
                {document.pages ? ` · ${document.pages} pages` : ""}
              </span>
              <button
                className="button button--secondary"
                disabled={disabled}
                onClick={() => onRemove(document.document_id)}
                type="button"
              >
                Delete
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
