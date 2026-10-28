/** Check for a JSON object that is safe to render as key/value fields. */
function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Render nested JSON data as readable fields without changing its values. */
function FigureValue({ value }) {
  if (Array.isArray(value)) {
    const items = [];
    for (let index = 0; index < value.length; index += 1) {
      items.push(
        <li key={index}>
          <FigureValue value={value[index]} />
        </li>,
      );
    }
    return <ol className="figure-value-list">{items}</ol>;
  }

  if (isRecord(value)) {
    const fields = [];
    for (const [key, fieldValue] of Object.entries(value)) {
      fields.push(
        <div className="figure-field" key={key}>
          <dt>{key}</dt>
          <dd>
            <FigureValue value={fieldValue} />
          </dd>
        </div>,
      );
    }
    return <dl className="figure-fields">{fields}</dl>;
  }

  return <span>{value === null ? "null" : String(value)}</span>;
}

/** Recognize the analysis figure structure observed in the live fixtures. */
function isAnalysisFigure(figure) {
  return (
    isRecord(figure) &&
    typeof figure.analysis === "string" &&
    Object.hasOwn(figure, "period") &&
    Array.isArray(figure.data)
  );
}

/** Render figures in a collapsed section, with a generic JSON fallback. */
export function FiguresView({ figures }) {
  const figureItems = [];
  for (let index = 0; index < figures.length; index += 1) {
    const figure = figures[index];
    if (isAnalysisFigure(figure)) {
      const fields = {};
      for (const [key, value] of Object.entries(figure)) {
        if (key !== "analysis") {
          fields[key] = value;
        }
      }

      figureItems.push(
        <li key={`${figure.analysis}-${index}`}>
          <article className="figure-card">
            <h4>{figure.analysis}</h4>
            <FigureValue value={fields} />
          </article>
        </li>,
      );
      continue;
    }

    figureItems.push(
      <li key={`unknown-${index}`}>
        <pre className="figure-fallback">
          {JSON.stringify(figure, null, 2) ?? String(figure)}
        </pre>
      </li>,
    );
  }

  return (
    <details className="figures-view">
      <summary>Figures ({figures.length})</summary>
      <ol className="figure-list">{figureItems}</ol>
    </details>
  );
}
