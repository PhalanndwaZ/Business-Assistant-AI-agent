const randFormatter = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** Convert cents to South African rand only for `money_cents` charts. */
export function formatChartValue(value, unit) {
  if (typeof value !== "number") {
    return value === null ? "null" : String(value);
  }
  if (unit === "money_cents") {
    const formatted = randFormatter.format(Math.abs(value) / 100);
    return value < 0 ? `-R${formatted}` : `R${formatted}`;
  }
  return String(value);
}
