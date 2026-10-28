const MAX_PREVIEW_ROWS = 5;

/** Check for a JSON object without treating arrays as records. */
function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/** Convert API field names into concise labels for people. */
function formatLabel(value) {
  return String(value)
    .replace(/_/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

/** Format date-shaped values for the evidence summary. */
function formatValue(value, fieldName = "") {
  if (value === null || value === undefined) {
    return "Not available";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  if (typeof value === "number") {
    if (/percent|percentage|growth_rate/i.test(fieldName)) {
      return `${Number(value.toFixed(2))}%`;
    }
    if (Number.isInteger(value)) {
      return new Intl.NumberFormat().format(value);
    }
    return new Intl.NumberFormat(undefined, {
      maximumFractionDigits: 2,
    }).format(value);
  }
  if (typeof value === "string") {
    const isoDate = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (isoDate) {
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "medium",
        timeZone: "UTC",
      }).format(
        new Date(
          Date.UTC(
            Number(isoDate[1]),
            Number(isoDate[2]) - 1,
            Number(isoDate[3]),
          ),
        ),
      );
    }
    const isoMonth = /^(\d{4})-(\d{2})$/.exec(value);
    if (isoMonth) {
      return new Intl.DateTimeFormat(undefined, {
        month: "long",
        year: "numeric",
        timeZone: "UTC",
      }).format(
        new Date(Date.UTC(Number(isoMonth[1]), Number(isoMonth[2]) - 1, 1)),
      );
    }
    return value;
  }
  return String(value);
}

/** Render nested values with labels rather than exposing JSON syntax. */
function FigureValue({ value, fieldName = "" }) {
  if (Array.isArray(value)) {
    return (
      <ul className="figure-value-list">
        {value.map((item, index) => (
          <li key={`${fieldName}-${index}`}>
            <FigureValue value={item} fieldName={fieldName} />
          </li>
        ))}
      </ul>
    );
  }

  if (isRecord(value)) {
    return (
      <dl className="figure-fields">
        {Object.entries(value).map(([key, fieldValue]) => (
          <div className="figure-field" key={key}>
            <dt>{formatLabel(key)}</dt>
            <dd>
              <FigureValue value={fieldValue} fieldName={key} />
            </dd>
          </div>
        ))}
      </dl>
    );
  }

  return <span>{formatValue(value, fieldName)}</span>;
}

/** Build a preview table with a stable set of human-readable columns. */
function FigureTable({ rows, totalRows, dataset }) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  if (rows.length === 0 || columns.length === 0) {
    return <p className="figure-empty">No rows were returned for preview.</p>;
  }

  return (
    <div className="figure-table-wrap">
      <table className="figure-table">
        <caption>
          Showing {rows.length} of {totalRows} returned{" "}
          {dataset ? `${dataset} ` : ""}records
        </caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column} scope="col">
                {formatLabel(column)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column) => (
                <td key={column}>
                  <FigureValue value={row[column]} fieldName={column} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Summarize a dataset query and tuck returned rows into a small preview. */
function DatasetFigure({ figure }) {
  const dataset =
    typeof figure.dataset === "string" ? figure.dataset : "Business data";
  const totalMatches =
    typeof figure.total_matches === "number" ? figure.total_matches : null;
  const rows = Array.isArray(figure.rows)
    ? figure.rows.filter(isRecord)
    : [];
  const previewRows = rows.slice(0, MAX_PREVIEW_ROWS);
  const countText =
    totalMatches === null
      ? `${rows.length} returned ${dataset} records`
      : `${new Intl.NumberFormat().format(totalMatches)} matching ${dataset}`;

  return (
    <article className="figure-card">
      <h4>{formatLabel(dataset)}</h4>
      <p className="figure-summary">{countText}</p>
      <details className="figure-preview">
        <summary>Preview records</summary>
        <FigureTable
          dataset={dataset}
          rows={previewRows}
          totalRows={rows.length}
        />
      </details>
    </article>
  );
}

/** Render one analysis as titled results with a compact result table. */
function AnalysisFigure({ figure }) {
  const data = figure.data.filter(isRecord);
  const period =
    isRecord(figure.period) && Object.keys(figure.period).length > 0
      ? figure.period
      : null;

  return (
    <article className="figure-card">
      <h4>{formatLabel(figure.analysis)}</h4>
      {period ? (
        <div className="figure-period">
          <FigureValue value={period} fieldName="period" />
        </div>
      ) : null}
      <FigureTable
        dataset=""
        rows={data.slice(0, MAX_PREVIEW_ROWS)}
        totalRows={data.length}
      />
      {data.length > MAX_PREVIEW_ROWS ? (
        <p className="figure-empty">
          Showing the first {MAX_PREVIEW_ROWS} of {data.length} results.
        </p>
      ) : null}
    </article>
  );
}

/** Render figures as concise summaries instead of raw JSON. */
export function FiguresView({ figures }) {
  const figureItems = figures.map((figure, index) => {
    if (isRecord(figure) && typeof figure.dataset === "string") {
      return (
        <li key={`dataset-${figure.dataset}-${index}`}>
          <DatasetFigure figure={figure} />
        </li>
      );
    }
    if (
      isRecord(figure) &&
      typeof figure.analysis === "string" &&
      Array.isArray(figure.data)
    ) {
      return (
        <li key={`analysis-${figure.analysis}-${index}`}>
          <AnalysisFigure figure={figure} />
        </li>
      );
    }
    return (
      <li key={`other-${index}`}>
        <article className="figure-card">
          <h4>Additional result</h4>
          <FigureValue value={figure} />
        </article>
      </li>
    );
  });

  return (
    <details className="figures-view">
      <summary>Figures ({figures.length})</summary>
      <ol className="figure-list">{figureItems}</ol>
    </details>
  );
}
