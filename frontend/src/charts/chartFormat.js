const usdFormatter = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Convert cents to dollars only when the chart explicitly uses `money_cents`. */
export function formatChartValue(value, unit) {
  if (typeof value !== "number") {
    return value === null ? "null" : String(value);
  }
  if (unit === "money_cents") {
    return `${usdFormatter.format(value / 100)} (${String(value)} cents)`;
  }
  return String(value);
}
