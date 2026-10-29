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

function isValidWaterfallEntry(entry) {
  return (
    entry !== null &&
    typeof entry === "object" &&
    typeof entry.label === "string" &&
    entry.label.trim() !== "" &&
    Number.isFinite(entry.value) &&
    (entry.kind === "total" || entry.kind === "delta")
  );
}

function getTotalRange(entry) {
  return {
    ...entry,
    positiveBase: 0,
    positiveRange: entry.value > 0 ? entry.value : 0,
    negativeBase: 0,
    negativeRange: entry.value < 0 ? entry.value : 0,
  };
}

function getDeltaRange(entry, previousTotal, nextTotal) {
  const low = Math.min(previousTotal, nextTotal);
  const high = Math.max(previousTotal, nextTotal);

  if (low >= 0) {
    return {
      ...entry,
      positiveBase: low,
      positiveRange: high - low,
      negativeBase: 0,
      negativeRange: 0,
    };
  }
  if (high <= 0) {
    return {
      ...entry,
      positiveBase: 0,
      positiveRange: 0,
      negativeBase: high,
      negativeRange: low - high,
    };
  }
  return {
    ...entry,
    positiveBase: 0,
    positiveRange: high,
    negativeBase: 0,
    negativeRange: low,
  };
}

function validateWaterfallSeries(series) {
  if (
    !Array.isArray(series) ||
    series.length < 3 ||
    !series.every(isValidWaterfallEntry) ||
    series[0].kind !== "total" ||
    series[series.length - 1].kind !== "total" ||
    series.slice(1, -1).some((entry) => entry.kind !== "delta")
  ) {
    return { status: "invalid", series: [] };
  }

  let runningTotal = series[0].value;
  const chartSeries = [getTotalRange(series[0])];

  for (const step of series.slice(1, -1)) {
    const nextTotal = runningTotal + step.value;
    if (!Number.isFinite(nextTotal)) {
      return { status: "invalid", series: [] };
    }
    chartSeries.push(getDeltaRange(step, runningTotal, nextTotal));
    runningTotal = nextTotal;
  }

  const endingTotal = series[series.length - 1].value;
  if (runningTotal !== endingTotal) {
    return { status: "mismatch", series: [] };
  }

  chartSeries.push(getTotalRange(series[series.length - 1]));
  return { status: "valid", series: chartSeries };
}

function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

function WaterfallRangeShape({ highlight, payload, ...shapeProps }) {
  return (
    <Rectangle
      {...shapeProps}
      fill={payload?.label === highlight ? HIGHLIGHT_FILL : MUTED_FILL}
    />
  );
}

function WaterfallTooltip({ active, payload, unit }) {
  const point = payload?.find(
    (item) =>
      item?.payload &&
      Number.isFinite(item.payload.value) &&
      (item.payload.kind === "total" || item.payload.kind === "delta"),
  )?.payload;

  if (!active || !point) {
    return null;
  }

  return (
    <div className="waterfall-view__tooltip">
      <p className="waterfall-view__tooltip-label">{point.label}</p>
      <p>
        <strong>{point.kind === "delta" ? "Change" : "Total"}:</strong>{" "}
        {formatChartValue(point.value, unit)}
      </p>
    </div>
  );
}

/** Render validated totals and deltas as floating waterfall bars. */
export function WaterfallView({ chart }) {
  const result = validateWaterfallSeries(chart?.series);
  const series = result.series;
  const axisLabel = getValueAxisLabel(chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Waterfall chart";
  const highlightedItem =
    typeof chart?.highlight === "string" &&
    series.some((item) => item.label === chart.highlight)
      ? chart.highlight
      : null;

  if (result.status !== "valid") {
    const note =
      result.status === "mismatch"
        ? "The supplied waterfall steps do not add up to the ending total. No chart is drawn; view the data table below."
        : "Valid starting total, delta steps, and ending total were not provided. No chart is drawn; view the data table below.";
    return <p className="waterfall-view__empty">{note}</p>;
  }

  return (
    <div className="waterfall-view">
      {highlightedItem ? (
        <p className="waterfall-view__highlight">
          Highlighted: <strong>{highlightedItem}</strong>
        </p>
      ) : null}
      <div aria-label={altText} className="waterfall-view__chart" role="img">
        <ResponsiveContainer width="100%" height={256}>
          <BarChart
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
              <Label offset={-12} position="insideBottom" value="Step" />
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
              content={<WaterfallTooltip unit={chart?.unit} />}
              isAnimationActive={false}
            />
            <Bar
              dataKey="positiveBase"
              fill="transparent"
              isAnimationActive={false}
              legendType="none"
              stackId="waterfall"
            />
            <Bar
              dataKey="positiveRange"
              isAnimationActive={false}
              legendType="none"
              name="Value"
              shape={<WaterfallRangeShape highlight={highlightedItem} />}
              stackId="waterfall"
            />
            <Bar
              dataKey="negativeBase"
              fill="transparent"
              isAnimationActive={false}
              legendType="none"
              stackId="waterfall"
            />
            <Bar
              dataKey="negativeRange"
              isAnimationActive={false}
              legendType="none"
              name="Value"
              shape={<WaterfallRangeShape highlight={highlightedItem} />}
              stackId="waterfall"
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
