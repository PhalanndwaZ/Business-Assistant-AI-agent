import { requestJson } from "./client.js";
import { normalizeApiError } from "./errors.js";

/** Confirm a non-sensitive department summary record is complete. */
function isDepartmentSummary(summary) {
  return (
    summary !== null &&
    typeof summary === "object" &&
    typeof summary.period === "string" &&
    typeof summary.department === "string" &&
    typeof summary.status === "string" &&
    typeof summary.summary === "string" &&
    typeof summary.metric === "string" &&
    (summary.value === undefined ||
      summary.value === null ||
      (Number.isInteger(summary.value) && summary.value >= 0)) &&
    (summary.value_percent === undefined ||
      summary.value_percent === null ||
      (typeof summary.value_percent === "number" &&
        Number.isFinite(summary.value_percent)))
  );
}

/** Fetch and validate the safe, aggregate-only manager department overview. */
export async function getManagerOverview({ signal } = {}) {
  const payload = await requestJson("/manager/overview", { signal });
  if (
    payload === null ||
    typeof payload !== "object" ||
    payload.synthetic !== true ||
    typeof payload.currency !== "string" ||
    !Array.isArray(payload.department_overview) ||
    !payload.department_overview.every(isDepartmentSummary) ||
    !Array.isArray(payload.sales_performance) ||
    !payload.sales_performance.every(
      (row) =>
        row !== null &&
        typeof row === "object" &&
        typeof row.month === "string" &&
        Number.isInteger(row.revenue_cents) &&
        Number.isInteger(row.target_revenue_cents) &&
        Number.isInteger(row.completed_orders),
    ) ||
    !Array.isArray(payload.headcount_by_department) ||
    !payload.headcount_by_department.every(
      (row) =>
        row !== null &&
        typeof row === "object" &&
        typeof row.department === "string" &&
        Number.isInteger(row.headcount),
    )
  ) {
    throw normalizeApiError({ body: payload, invalidResponse: true });
  }
  return payload;
}
