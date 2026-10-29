import {
  Area,
  AreaChart,
  CartesianGrid,
  Label,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChartValue } from "../../charts/chartFormat.js";

const LINE_COLOR = "var(--color-text-muted)";
const HIGHLIGHT_COLOR = "var(--color-accent)";

function isValidRangePoint(point) {
  return (
    point !== null &&
    typeof point === "object" &&
    typeof point.label === "string" &&
    point.label.trim() !== "" &&
    Number.isFinite(point.value) &&
    Number.isFinite(point.lower) &&
    Number.isFinite(point.upper) &&
    point.lower <= point.upper
  );
}

function getRangeSeries(series) {
  if (
    !Array.isArray(series) ||
    series.length === 0 ||
    !series.every(isValidRangePoint)
  ) {
    return [];
  }

  return series.map((point) => ({
    ...point,
    positiveBase: Math.max(point.lower, 0),
    positiveRange: Math.max(point.upper, 0) - Math.max(point.lower, 0),
    negativeBase: Math.min(point.upper, 0),
    negativeRange: Math.min(point.lower, 0) - Math.min(point.upper, 0),
  }));
}

function getAnnotations(annotations) {
  if (!Array.isArray(annotations)) {
    return [];
  }

  return annotations.filter(
    (annotation) =>
      annotation !== null &&
      typeof annotation === "object" &&
      typeof annotation.label === "string" &&
      annotation.label.trim() !== "" &&
      (typeof annotation.value === "string" ||
        Number.isFinite(annotation.value)),
  );
}

function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

function ExpectedRangePoint({ cx, cy, payload }) {
  if (!Number.isFinite(cx) || !Number.isFinite(cy)) {
    return null;
  }

  const isFlagged = payload?.flagged === true;
  return (
    <circle
      cx={cx}
      cy={cy}
      fill={isFlagged ? HIGHLIGHT_COLOR : "var(--color-surface)"}
      r={isFlagged ? 6 : 3.5}
      stroke={isFlagged ? HIGHLIGHT_COLOR : LINE_COLOR}
      strokeWidth={isFlagged ? 2 : 1.5}
    />
  );
}

function ExpectedRangeTooltip({ active, payload, unit }) {
  const point = payload?.find(
    (item) => item?.payload && Number.isFinite(item.payload.value),
  )?.payload;

  if (!active || !point) {
    return null;
  }

  return (
    <div className="band-line-view__tooltip">
      <p className="band-line-view__tooltip-label">{point.label}</p>
      <p>
        <strong>Value:</strong> {formatChartValue(point.value, unit)}
      </p>
      <p>
        <strong>Expected range:</strong>{" "}
        {formatChartValue(point.lower, unit)}–{formatChartValue(point.upper, unit)}
      </p>
      {point.flagged === true ? (
        <p>
          <strong>Flagged:</strong> Yes
        </p>
      ) : null}
    </div>
  );
}

/** Render only the expected limits, flagged points, and annotations supplied. */
export function BandLineView({ chart }) {
  const series = getRangeSeries(chart?.series);
  const annotations = getAnnotations(chart?.annotations);
  const flaggedPeriods = series
    .filter((point) => point.flagged === true)
    .map((point) => point.label);
  const axisLabel = getValueAxisLabel(chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Line chart with expected range";

  if (series.length === 0) {
    return (
      <p className="band-line-view__empty">
        Valid expected-range data was not provided. View the data table below.
      </p>
    );
  }

  return (
    <div className="band-line-view">
      <div className="band-line-view__legend" aria-label="Chart legend">
        <span>
          <span
            aria-hidden="true"
            className="band-line-view__legend-swatch band-line-view__legend-swatch--range"
          />
          Expected range
        </span>
        <span>
          <span
            aria-hidden="true"
            className="band-line-view__legend-swatch band-line-view__legend-swatch--value"
          />
          Value
        </span>
      </div>
      {flaggedPeriods.length > 0 ? (
        <p className="band-line-view__flag">
          Flagged by the chart data:{" "}
          <strong>{flaggedPeriods.join(", ")}</strong>
        </p>
      ) : null}
      {annotations.length > 0 ? (
        <div
          aria-label="Chart annotations"
          className="band-line-view__annotations"
        >
          {annotations.map((annotation, index) => (
            <p
              className="band-line-view__annotation"
              key={`${annotation.label}-${index}`}
            >
              <strong>{annotation.label}:</strong>{" "}
              {formatChartValue(annotation.value, chart?.unit)}
            </p>
          ))}
        </div>
      ) : null}
      <div aria-label={altText} className="band-line-view__chart" role="img">
        <ResponsiveContainer width="100%" height={256}>
          <AreaChart
            accessibilityLayer
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
              content={<ExpectedRangeTooltip unit={chart?.unit} />}
              isAnimationActive={false}
            />
            <Area
              dataKey="positiveBase"
              fill="transparent"
              isAnimationActive={false}
              stackId="expected-range"
              stroke="transparent"
              type="linear"
            />
            <Area
              dataKey="positiveRange"
              fill={HIGHLIGHT_COLOR}
              fillOpacity={0.18}
              isAnimationActive={false}
              stackId="expected-range"
              stroke="transparent"
              type="linear"
            />
            <Area
              dataKey="negativeBase"
              fill="transparent"
              isAnimationActive={false}
              stackId="expected-range"
              stroke="transparent"
              type="linear"
            />
            <Area
              dataKey="negativeRange"
              fill={HIGHLIGHT_COLOR}
              fillOpacity={0.18}
              isAnimationActive={false}
              stackId="expected-range"
              stroke="transparent"
              type="linear"
            />
            <Line
              dataKey="value"
              dot={<ExpectedRangePoint />}
              isAnimationActive={false}
              name="Value"
              stroke={LINE_COLOR}
              strokeWidth={2}
              type="linear"
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
