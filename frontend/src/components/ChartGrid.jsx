import { ChartCard } from "./ChartCard.jsx";

/** Display up to three chart cards in the order provided by the API. */
export function ChartGrid({ charts }) {
  if (!Array.isArray(charts) || charts.length === 0) {
    return null;
  }
  const visibleCharts = charts
    .filter(
      (chart) =>
        chart !== null && typeof chart === "object" && !Array.isArray(chart),
    )
    .slice(0, 3);
  if (visibleCharts.length === 0) {
    return null;
  }

  return (
    <section className="chart-grid" aria-label="Charts">
      {visibleCharts.map((chart, index) => (
        <ChartCard chart={chart} key={chart.id || `${chart.type}-${index}`} />
      ))}
    </section>
  );
}
