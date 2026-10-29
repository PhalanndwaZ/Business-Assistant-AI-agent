import { formatChartValue } from "../charts/chartFormat.js";

function isRecord(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function formatFieldLabel(field) {
  return field
    .replace(/\[(\d+)\]/g, " $1")
    .replace(/[._-]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function appendValue(rows, context, field, value, unit) {
  if (Array.isArray(value)) {
    value.forEach((item, index) => {
      appendValue(rows, context, `${field}[${index}]`, item, unit);
    });
    return;
  }
  if (isRecord(value)) {
    for (const [key, nestedValue] of Object.entries(value)) {
      appendValue(
        rows,
        context,
        field ? `${field}.${key}` : key,
        nestedValue,
        unit,
      );
    }
    return;
  }
  rows.push({
    ...context,
    field,
    value: formatChartValue(value, unit),
  });
}

function appendRecord(rows, record, series, fallbackLabel, defaultUnit) {
  if (!isRecord(record)) {
    appendValue(rows, { series, label: fallbackLabel }, "Value", record, defaultUnit);
    return;
  }
  const label =
    typeof record.label === "string" ? record.label : fallbackLabel;
  const unit = typeof record.unit === "string" ? record.unit : defaultUnit;
  const context = { series, label };
  for (const [field, value] of Object.entries(record)) {
    if (field !== "label" && field !== "unit" && field !== "points") {
      appendValue(rows, context, field, value, unit);
    }
  }
}

function getChartRows(chart) {
  const rows = [];
  if (Array.isArray(chart?.series)) {
    for (const series of chart.series) {
      if (!isRecord(series)) {
        appendValue(rows, { series: "", label: "" }, "Value", series, chart.unit);
        continue;
      }
      const seriesName =
        typeof series.label === "string" ? series.label : "";
      if (Array.isArray(series.points)) {
        for (const point of series.points) {
          appendRecord(rows, point, seriesName, seriesName, series.unit || chart.unit);
        }
      } else {
        appendRecord(rows, series, "", "", chart.unit);
      }
    }
  }
  if (Array.isArray(chart?.annotations)) {
    for (const annotation of chart.annotations) {
      appendRecord(rows, annotation, "Annotation", "", chart.unit);
    }
  }
  if (rows.length === 0 && Object.hasOwn(chart || {}, "data")) {
    const records = Array.isArray(chart.data) ? chart.data : [chart.data];
    records.forEach((record, index) => {
      appendRecord(rows, record, "", `Row ${index + 1}`, chart.unit);
    });
  }
  return rows;
}

/** Show exact chart data in a compact, accessible table. */
export function ChartTable({ chart }) {
  const rows = getChartRows(chart);
  const title =
    typeof chart?.title === "string" && chart.title
      ? chart.title
      : "Chart";

  return (
    <details className="chart-table">
      <summary>View data</summary>
      {rows.length > 0 ? (
        <div className="chart-table__scroll">
          <table aria-label={`${title} data`}>
            <caption className="visually-hidden">{title} data</caption>
            <thead>
              <tr>
                <th scope="col">Series</th>
                <th scope="col">Label</th>
                <th scope="col">Field</th>
                <th scope="col">Value</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.series}-${row.label}-${row.field}-${index}`}>
                  <td>{row.series || "—"}</td>
                  <td>{row.label || "—"}</td>
                  <td>{row.field ? formatFieldLabel(row.field) : "—"}</td>
                  <td>{row.value}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="chart-table__empty">No chart data was provided.</p>
      )}
    </details>
  );
}
