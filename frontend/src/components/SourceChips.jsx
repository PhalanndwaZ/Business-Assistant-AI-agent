/** Present source names and unknown source values as readable chips. */
export function SourceChips({ sources }) {
  const chips = [];
  for (let index = 0; index < sources.length; index += 1) {
    const source = sources[index];
    const label =
      typeof source === "string"
        ? source
        : JSON.stringify(source) ?? String(source);
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
