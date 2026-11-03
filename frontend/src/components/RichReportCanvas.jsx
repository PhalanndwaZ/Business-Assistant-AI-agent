import { useEffect, useId, useRef } from "react";

function formatValue(value, format) {
  const numeric = typeof value === "number" ? value : null;
  if (numeric === null) {
    return String(value);
  }
  if (format === "money") {
    return `R${new Intl.NumberFormat("en-US", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(numeric / 100)}`;
  }
  if (format === "percent") {
    return `${new Intl.NumberFormat("en-US", {
      maximumFractionDigits: 2,
    }).format(numeric * 100)}%`;
  }
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 2,
  }).format(numeric);
}

function RevenueChart({ chart }) {
  const width = 720;
  const height = 280;
  const padding = { left: 64, right: 24, top: 24, bottom: 48 };
  const values = chart.y.map((value) => Number(value));
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 1);
  const range = maximum - minimum || 1;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const points = values.map((value, index) => {
    const x =
      padding.left +
      (values.length === 1 ? plotWidth / 2 : (index / (values.length - 1)) * plotWidth);
    const y =
      padding.top +
      ((maximum - value) / range) * plotHeight;
    return { x, y, value };
  });
  const polygon = points.map(({ x, y }) => `${x},${y}`).join(" ");

  return (
    <figure className="rich-report__chart">
      <figcaption>{chart.title}</figcaption>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={chart.title}>
        {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
          const y = padding.top + ratio * plotHeight;
          return <line key={ratio} x1={padding.left} x2={width - padding.right} y1={y} y2={y} />;
        })}
        <polygon points={`${padding.left},${height - padding.bottom} ${polygon} ${width - padding.right},${height - padding.bottom}`} />
        <polyline points={polygon} />
        {points.map((point, index) => (
          <g key={`${chart.x[index]}-${index}`}>
            <circle cx={point.x} cy={point.y} r={index === values.length - 1 && chart.highlight_last ? 7 : 4} />
            <text x={point.x} y={height - 18} textAnchor="middle">{chart.x[index]}</text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

export function RichReportCanvas({ report, onClose }) {
  const dialogRef = useRef(null);
  const titleId = useId();

  useEffect(() => {
    dialogRef.current?.focus();
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        onClose();
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!report) {
    return null;
  }

  return (
    <div className="rich-report-backdrop" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) {
        onClose();
      }
    }}>
      <section
        className="rich-report"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex="-1"
        ref={dialogRef}
      >
        <header className="rich-report__header">
          <div>
            <span>Business report</span>
            <h2 id={titleId}>{report.title}</h2>
            <p>{report.period_label} · As of {report.as_of_date}</p>
          </div>
          <button className="rich-report__close" type="button" onClick={onClose} aria-label="Close report">
            ×
          </button>
        </header>

        <div className="rich-report__body">
          <section className="rich-report__figures" aria-label="Key figures">
            {report.key_figures.map((figure, index) => (
              <article key={`${figure.label}-${index}`}>
                <span>{figure.label}</span>
                <strong>{formatValue(figure.value, figure.format)}</strong>
              </article>
            ))}
          </section>

          <section>
            <h3>Executive summary</h3>
            {report.summary.map((paragraph, index) => <p key={index}>{paragraph}</p>)}
          </section>

          {report.chart ? <RevenueChart chart={report.chart} /> : null}

          {report.tables.map((table, tableIndex) => (
            <section key={`${table.title}-${tableIndex}`}>
              <h3>{table.title}</h3>
              <div className="rich-report__table-wrap">
                <table>
                  <thead>
                    <tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr>
                  </thead>
                  <tbody>
                    {table.rows.map((row, rowIndex) => (
                      <tr key={rowIndex}>
                        {row.map((value, columnIndex) => (
                          <td key={columnIndex}>{formatValue(value, table.formats[columnIndex])}</td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ))}

          <section>
            <h3>Findings and actions</h3>
            <div className="rich-report__findings">
              {report.findings.map((finding, index) => (
                <article key={index}>
                  <span>{String(index + 1).padStart(2, "0")}</span>
                  <div>
                    <h4>{finding.finding}</h4>
                    <p><strong>Evidence:</strong> {finding.evidence}</p>
                    <p><strong>Action:</strong> {finding.action}</p>
                    <p><strong>Caveat:</strong> {finding.caveat}</p>
                  </div>
                </article>
              ))}
            </div>
          </section>

          {report.notes.length > 0 ? (
            <section>
              <h3>Notes</h3>
              <ul>{report.notes.map((note, index) => <li key={index}>{note}</li>)}</ul>
            </section>
          ) : null}
        </div>
      </section>
    </div>
  );
}
