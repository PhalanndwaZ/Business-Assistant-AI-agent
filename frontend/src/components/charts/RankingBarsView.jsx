import {
  Bar,
  BarChart,
  CartesianGrid,
  Label,
  Rectangle,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChartValue } from "../../charts/chartFormat.js";

const HIGHLIGHT_FILL = "var(--color-accent)";
const MUTED_FILL = "var(--color-text-muted)";

/** Sort valid ranking entries by descending source value without changing them. */
function sortRankingSeries(series) {
  return series
    .map((entry, index) => ({ entry, index }))
    .filter(
      ({ entry }) =>
        entry !== null &&
        typeof entry === "object" &&
        typeof entry.label === "string" &&
        Number.isFinite(entry.value),
    )
    .sort(
      (left, right) =>
        right.entry.value - left.entry.value || left.index - right.index,
    )
    .map(({ entry }) => ({ label: entry.label, value: entry.value }));
}

/** Describe the unit rendered along the numeric value axis. */
function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

/** Draw the highlighted ranking item in accent color and others in muted color. */
function RankingBarShape({ highlight, payload, ...shapeProps }) {
  return (
    <Rectangle
      {...shapeProps}
      fill={payload?.label === highlight ? HIGHLIGHT_FILL : MUTED_FILL}
    />
  );
}

/** Render ranked horizontal bars using only the values supplied by the API. */
export function RankingBarsView({ chart }) {
  const series = sortRankingSeries(
    Array.isArray(chart?.series) ? chart.series : [],
  );
  const axisLabel = getValueAxisLabel(chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Ranking bar chart";
  const highlightedItem =
    typeof chart?.highlight === "string" &&
    series.some((item) => item.label === chart.highlight)
      ? chart.highlight
      : null;
  const chartHeight = Math.max(176, series.length * 48 + 48);

  /** Format tooltip values with the chart's declared unit. */
  const formatTooltipValue = (value) =>
    formatChartValue(value, chart?.unit);

  if (series.length === 0) {
    return (
      <p className="ranking-bars-view__empty">
        No ranking data was provided.
      </p>
    );
  }

  return (
    <div className="ranking-bars-view">
      {highlightedItem ? (
        <p className="ranking-bars-view__highlight">
          Highlighted: <strong>{highlightedItem}</strong>
        </p>
      ) : null}
      <div
        aria-label={altText}
        className="ranking-bars-view__chart"
        role="img"
      >
        <ResponsiveContainer width="100%" height={chartHeight}>
          <BarChart
            data={series}
            layout="vertical"
            margin={{ top: 8, right: 12, bottom: 30, left: 0 }}
          >
            <CartesianGrid
              horizontal={false}
              stroke="var(--color-border)"
            />
            <XAxis
              domain={[0, "dataMax"]}
              tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
              type="number"
            >
              <Label
                offset={-12}
                position="insideBottom"
                value={axisLabel}
              />
            </XAxis>
            <YAxis
              dataKey="label"
              tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
              type="category"
              width={112}
            />
            <Tooltip
              formatter={formatTooltipValue}
              isAnimationActive={false}
            />
            <Bar
              dataKey="value"
              isAnimationActive={false}
              name="Value"
              radius={[0, 4, 4, 0]}
              shape={<RankingBarShape highlight={highlightedItem} />}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
