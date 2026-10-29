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

function getComparisonSeries(series) {
  if (
    !Array.isArray(series) ||
    series.length !== 2 ||
    series.some(
      (entry) =>
        entry === null ||
        typeof entry !== "object" ||
        typeof entry.label !== "string" ||
        !entry.label.trim() ||
        !Number.isFinite(entry.value),
    ) ||
    series[0].label === series[1].label
  ) {
    return [];
  }

  return series.map(({ label, value }) => ({ label, value }));
}

function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

function ComparisonBarShape({ highlight, payload, ...shapeProps }) {
  return (
    <Rectangle
      {...shapeProps}
      fill={payload?.label === highlight ? HIGHLIGHT_FILL : MUTED_FILL}
    />
  );
}

function getComparisonAnnotations(annotations) {
  if (!Array.isArray(annotations)) {
    return [];
  }

  return annotations.filter(
    (annotation) =>
      annotation !== null &&
      typeof annotation === "object" &&
      typeof annotation.label === "string" &&
      annotation.label.trim() &&
      Number.isFinite(annotation.value),
  );
}

/** Render the supplied period values and change annotations without recalculation. */
export function CompareBarsView({ chart }) {
  const series = getComparisonSeries(chart?.series);
  const annotations = getComparisonAnnotations(chart?.annotations);
  const axisLabel = getValueAxisLabel(chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Comparison bar chart";
  const highlightedItem =
    typeof chart?.highlight === "string" &&
    series.some((item) => item.label === chart.highlight)
      ? chart.highlight
      : null;
  const formatTooltipValue = (value) => formatChartValue(value, chart?.unit);

  if (series.length !== 2) {
    return (
      <p className="compare-bars-view__empty">
        Two valid comparison periods were not provided.
      </p>
    );
  }

  return (
    <div className="compare-bars-view">
      {highlightedItem ? (
        <p className="compare-bars-view__highlight">
          Highlighted: <strong>{highlightedItem}</strong>
        </p>
      ) : null}
      {annotations.length > 0 ? (
        <div
          aria-label="Comparison annotations"
          className="compare-bars-view__annotations"
        >
          {annotations.map((annotation, index) => (
            <p
              className="compare-bars-view__annotation"
              key={`${annotation.label}-${index}`}
            >
              <strong>{annotation.label}:</strong>{" "}
              {formatChartValue(annotation.value, chart?.unit)}
            </p>
          ))}
        </div>
      ) : (
        <p className="compare-bars-view__empty">
          No comparison change annotation was provided.
        </p>
      )}
      <div
        aria-label={altText}
        className="compare-bars-view__chart"
        role="img"
      >
        <ResponsiveContainer width="100%" height={256}>
          <BarChart
            data={series}
            margin={{ top: 12, right: 12, bottom: 30, left: 18 }}
          >
            <CartesianGrid
              stroke="var(--color-border)"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
              type="category"
            >
              <Label offset={-12} position="insideBottom" value="Period" />
            </XAxis>
            <YAxis
              tick={{ fill: "var(--color-text-muted)", fontSize: 11 }}
              type="number"
            >
              <Label
                angle={-90}
                position="insideLeft"
                value={axisLabel}
              />
            </YAxis>
            <Tooltip
              formatter={formatTooltipValue}
              isAnimationActive={false}
              labelFormatter={(label) => String(label)}
            />
            <Bar
              dataKey="value"
              isAnimationActive={false}
              name="Value"
              radius={[4, 4, 0, 0]}
              shape={<ComparisonBarShape highlight={highlightedItem} />}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
