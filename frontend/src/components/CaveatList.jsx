/** Keep evidence caveats visible in an amber list beneath an answer. */
export function CaveatList({ caveats }) {
  const items = [];
  for (let index = 0; index < caveats.length; index += 1) {
    const caveat = caveats[index];
    const content =
      typeof caveat === "string"
        ? caveat
        : JSON.stringify(caveat) ?? String(caveat);
    items.push(<li key={`${index}-${content}`}>{content}</li>);
  }

  return (
    <section className="caveat-list" aria-label="Caveats">
      <h3>Caveats</h3>
      <ul>{items}</ul>
    </section>
  );
}
