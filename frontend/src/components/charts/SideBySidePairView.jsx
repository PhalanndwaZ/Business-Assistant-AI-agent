import {
  CartesianGrid,
  Label,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChartValue } from "../../charts/chartFormat.js";

const LINE_COLOR = "var(--color-text-muted)";
const HIGHLIGHT_COLOR = "var(--color-accent)";

function getPairSeries(series, defaultUnit) {
  if (!Array.isArray(series) || series.length !== 2) {
    return [];
  }

  const metrics = series.map((metric) => {
    if (
      metric === null ||
      typeof metric !== "object" ||
      typeof metric.label !== "string" ||
      metric.label.trim() === "" ||
      !Array.isArray(metric.points) ||
      metric.points.length === 0 ||
      !metric.points.every(
        (point) =>
          point !== null &&
          typeof point === "object" &&
          typeof point.label === "string" &&
          point.label.trim() !== "" &&
          Number.isFinite(point.value),
      )
    ) {
      return null;
    }

    return {
      label: metric.label,
      unit:
        typeof metric.unit === "string" && metric.unit.trim()
          ? metric.unit
          : defaultUnit,
      points: metric.points.map(({ label, value }) => ({ label, value })),
    };
  });

  return metrics.every((metric) => metric !== null) &&
    metrics[0].label !== metrics[1].label
    ? metrics
    : [];
}

function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

function PairPeriodPoint({ cx, cy, highlight, payload }) {
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) {
    return null;
  }

  const isHighlighted = payload?.label === highlight;
  return (
    <circle
      cx={cx}
      cy={cy}
      fill={isHighlighted ? HIGHLIGHT_COLOR : "var(--color-surface)"}
      r={isHighlighted ? 6 : 3.5}
      stroke={isHighlighted ? HIGHLIGHT_COLOR : LINE_COLOR}
      strokeWidth={isHighlighted ? 2 : 1.5}
    />
  );
}

function PairMetricChart({ altText, highlight, metric }) {
  const axisLabel = getValueAxisLabel(metric.unit);
  const highlightedPeriod =
    typeof highlight === "string" &&
    metric.points.some((point) => point.label === highlight)
      ? highlight
      : null;
  const formatTooltipValue = (value) =>
    formatChartValue(value, metric.unit);

  return (
    <section className="side-by-side-pair-view__metric">
      <h4>{metric.label}</h4>
      {highlightedPeriod ? (
        <p className="side-by-side-pair-view__highlight">
          Highlighted period: <strong>{highlightedPeriod}</strong>
        </p>
      ) : null}
      <div
        aria-label={`${metric.label}. ${altText}`}
        className="side-by-side-pair-view__chart"
        role="img"
      >
        <ResponsiveContainer width="100%" height={232}>
          <LineChart
            accessibilityLayer
            data={metric.points}
            margin={{ top: 10, right: 8, bottom: 30, left: 10 }}
          >
            <CartesianGrid
              stroke="var(--color-border)"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
              type="category"
            >
              <Label offset={-12} position="insideBottom" value="Period" />
            </XAxis>
            <YAxis
              tick={{ fill: "var(--color-text-muted)", fontSize: 10 }}
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
            <Line
              activeDot={{
                fill: HIGHLIGHT_COLOR,
                r: 5,
                stroke: "var(--color-surface)",
                strokeWidth: 2,
              }}
              dataKey="value"
              dot={<PairPeriodPoint highlight={highlightedPeriod} />}
              isAnimationActive={false}
              name="Value"
              stroke={LINE_COLOR}
              strokeWidth={2}
              type="linear"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

/** Render exactly two metric series in a responsive pair. */
export function SideBySidePairView({ chart }) {
  const series = getPairSeries(chart?.series, chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Side-by-side chart pair";

  if (series.length !== 2) {
    return (
      <p className="side-by-side-pair-view__empty">
        Two valid metric series were not provided. View the data table below.
      </p>
    );
  }

  return (
    <div className="side-by-side-pair-view">
      <div className="side-by-side-pair-view__grid">
        {series.map((metric) => (
          <PairMetricChart
            altText={altText}
            highlight={chart?.highlight}
            key={metric.label}
            metric={metric}
          />
        ))}
      </div>
    </div>
  );
}
