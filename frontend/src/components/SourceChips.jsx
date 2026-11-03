/** Present citations as expandable links to their matching retrieved excerpts. */
export function SourceChips({ sources, evidenceChunks = [] }) {
  const chips = [];
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const sourceRecord =
      source !== null && typeof source === "object" && !Array.isArray(source)
        ? source
        : null;
    const origin = sourceRecord?.origin;
    const name =
      sourceRecord?.document_name || sourceRecord?.name || source;
    const page = sourceRecord?.page;
    const badge =
      origin === "uploaded"
        ? "Your document"
        : origin === "company"
          ? "Company"
          : null;
    const label =
      typeof source === "string"
        ? source
        : [
            badge,
            name,
            page !== undefined && page !== null ? `p. ${page}` : null,
          ]
            .filter(Boolean)
            .join(" · ") ||
          (JSON.stringify(source) ?? String(source));
    const matchingChunks = evidenceChunks.filter((chunk) => {
      if (typeof name !== "string" || chunk.document_name !== name) {
        return false;
      }
      if (origin && chunk.origin && chunk.origin !== origin) {
        return false;
      }
      return (
        page === null ||
        page === undefined ||
        chunk.page_number === page
      );
    });
    chips.push(
      <li className="source-citation" key={`${index}-${label}`}>
        <details>
          <summary className="source-chip">
            <span>{label}</span>
            <span aria-hidden="true" className="source-chip__indicator">
              +
            </span>
          </summary>
          <div className="source-citation__excerpt">
            <h4>
              {matchingChunks.length > 0
                ? "Supporting document excerpt"
                : "Source details"}
            </h4>
            {matchingChunks.length > 0 ? (
              matchingChunks.map((chunk, chunkIndex) => (
                <blockquote key={`${label}-${chunkIndex}`}>
                  <p>{chunk.text}</p>
                  {chunk.page_number !== undefined &&
                  chunk.page_number !== null ? (
                    <footer>Page {chunk.page_number}</footer>
                  ) : null}
                </blockquote>
              ))
            ) : (
              <p>
                No document excerpt was returned for this citation.
              </p>
            )}
          </div>
        </details>
      </li>,
    );
  }

  return (
    <section className="source-list" aria-label="Sources">
      <h4>Sources</h4>
      <ul>{chips}</ul>
    </section>
  );
}
