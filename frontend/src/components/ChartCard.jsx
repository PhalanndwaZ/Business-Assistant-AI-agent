import { getChartRenderer } from "../charts/chartRegistry.js";
import { ChartTable } from "./ChartTable.jsx";

function getSourceLine(source) {
  if (!source || typeof source.analysis !== "string" || !source.analysis) {
    return null;
  }
  return typeof source.as_of === "string" && source.as_of
    ? `From ${source.analysis}, as of ${source.as_of}`
    : `From ${source.analysis}`;
}

/** Render chart metadata, an implemented renderer, and its exact data table. */
export function ChartCard({ chart }) {
  const ChartRenderer = getChartRenderer(chart?.type);
  const title =
    typeof chart?.title === "string" && chart.title
      ? chart.title
      : "Untitled chart";
  const subtitle =
    typeof chart?.subtitle === "string" ? chart.subtitle : "";
  const sourceLine = getSourceLine(chart?.source);

  return (
    <article className="chart-card">
      <header className="chart-card__header">
        <h3>{title}</h3>
        {subtitle ? <p className="chart-card__subtitle">{subtitle}</p> : null}
      </header>
      {ChartRenderer ? (
        <div className="chart-card__visual">
          <ChartRenderer chart={chart} />
        </div>
      ) : (
        <p className="chart-card__note">
          Chart preview is not available yet. View the data table below.
        </p>
      )}
      {sourceLine ? (
        <p className="chart-card__source">{sourceLine}</p>
      ) : null}
      <ChartTable chart={chart} />
    </article>
  );
}
