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

function getPeriodSortValue(label) {
  const match = /^(\d{4})-(\d{2})(?:-(\d{2}))?$/.exec(label);
  if (!match) {
    return null;
  }

  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = match[3] ? Number(match[3]) : 0;
  const isLeapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth =
    month === 2 ? (isLeapYear ? 29 : 28) : [4, 6, 9, 11].includes(month) ? 30 : 31;
  if (
    month < 1 ||
    month > 12 ||
    day < 0 ||
    (day > 0 && day > daysInMonth)
  ) {
    return null;
  }

  return year * 372 + month * 31 + day;
}

/** Sort ISO-labelled periods chronologically while retaining source order otherwise. */
function getOrderedPeriods(series) {
  const periods = series
    .map((period, index) => ({ period, index }))
    .filter(
      ({ period }) =>
        period !== null &&
        typeof period === "object" &&
        typeof period.label === "string" &&
        Number.isFinite(period.value),
    );

  const sortValues = periods.map(({ period }) =>
    getPeriodSortValue(period.label),
  );
  if (sortValues.every((value) => value !== null)) {
    return periods
      .map((item, index) => ({
        ...item,
        sortValue: sortValues[index],
      }))
      .sort(
        (left, right) =>
          left.sortValue - right.sortValue || left.index - right.index,
      )
      .map(({ period }) => ({ label: period.label, value: period.value }));
  }

  return periods.map(({ period }) => ({
    label: period.label,
    value: period.value,
  }));
}

function getValueAxisLabel(unit) {
  if (unit === "money_cents") {
    return "Value (cents)";
  }
  return typeof unit === "string" && unit ? `Value (${unit})` : "Value";
}

function PeriodPoint({ cx, cy, highlight, payload }) {
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

/** Render time-series values in period order and emphasize the latest point. */
export function LineView({ chart }) {
  const periods = getOrderedPeriods(
    Array.isArray(chart?.series) ? chart.series : [],
  );
  const latestPeriod = periods[periods.length - 1]?.label || null;
  const axisLabel = getValueAxisLabel(chart?.unit);
  const altText =
    typeof chart?.alt_text === "string" && chart.alt_text
      ? chart.alt_text
      : "Line chart over time";

  const formatTooltipValue = (value) => formatChartValue(value, chart?.unit);

  if (periods.length === 0) {
    return (
      <p className="line-view__empty">No time-series data was provided.</p>
    );
  }

  return (
    <div className="line-view">
      {latestPeriod ? (
        <p className="line-view__highlight">
          Latest period highlighted: <strong>{latestPeriod}</strong>
        </p>
      ) : null}
      <div aria-label={altText} className="line-view__chart" role="img">
        <ResponsiveContainer width="100%" height={256}>
          <LineChart
            accessibilityLayer
            data={periods}
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
            <Line
              activeDot={{
                fill: HIGHLIGHT_COLOR,
                r: 5,
                stroke: "var(--color-surface)",
                strokeWidth: 2,
              }}
              dataKey="value"
              dot={<PeriodPoint highlight={latestPeriod} />}
              isAnimationActive={false}
              name="Value"
              stroke={LINE_COLOR}
              strokeWidth={2}
              type="linear"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
