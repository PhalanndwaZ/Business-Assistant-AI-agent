/** Present source names and unknown source values as readable chips. */
export function SourceChips({ sources }) {
  const chips = [];
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const origin = typeof source === "object" ? source.origin : null;
    const name = typeof source === "object" ? source.document_name || source.name : null;
    const page = typeof source === "object" ? source.page : null;
    const badge = origin === "uploaded" ? "Your document" : origin === "company" ? "Company" : null;
    const label = typeof source === "string"
      ? source
      : ([badge, name, page !== undefined && page !== null ? `p. ${page}` : null].filter(Boolean).join(" · ") || JSON.stringify(source)) ?? String(source);
    chips.push(
      <li className="source-chip" key={`${index}-${label}`}>
        {label}
      </li>,
    );
  }

  return (
    <section className="source-list" aria-label="Sources">
      <h3>Sources</h3>
      <ul>{chips}</ul>
    </section>
  );
}
