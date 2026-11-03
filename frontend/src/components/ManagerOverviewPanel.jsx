import { useEffect, useState } from "react";

import { getManagerOverview } from "../api/managerOverviewApi.js";

/** Show department-level summaries without employee or customer records. */
export function ManagerOverviewPanel() {
  const [overview, setOverview] = useState(null);
  const [error, setError] = useState("");

  useEffect(function loadOverview() {
    const controller = new AbortController();
    let active = true;

    async function fetchOverview() {
      try {
        const result = await getManagerOverview({ signal: controller.signal });
        if (active) {
          setOverview(result);
        }
      } catch (requestError) {
        if (active && requestError?.kind !== "cancelled") {
          setError(requestError?.detail || requestError.message);
        }
      }
    }

    fetchOverview();
    return function cancelOverviewLoad() {
      active = false;
      controller.abort();
    };
  }, []);

  if (error) {
    return (
      <section className="manager-overview" aria-labelledby="manager-overview-title">
        <h2 id="manager-overview-title">Department overview</h2>
        <p className="admin-users__error" role="alert">{error}</p>
      </section>
    );
  }
  if (!overview) {
    return (
      <section className="manager-overview" aria-labelledby="manager-overview-title">
        <h2 id="manager-overview-title">Department overview</h2>
        <p role="status">Loading department summaries...</p>
      </section>
    );
  }

  return (
    <section className="manager-overview" aria-labelledby="manager-overview-title">
      <div className="manager-overview__heading">
        <div>
          <p className="app-eyebrow">Manager</p>
          <h2 id="manager-overview-title">Department overview</h2>
        </div>
        <span className="manager-overview__period">
          {overview.department_overview[0]?.period || "Current summary"}
        </span>
      </div>
      <p className="manager-overview__notice">
        Illustrative summary data. Individual employee and customer records are
        not shown.
      </p>
      <div className="manager-overview__cards">
        {overview.department_overview.map((department) => (
          <article
            className="manager-overview__card"
            key={`${department.period}-${department.department}`}
          >
            <div className="manager-overview__card-heading">
              <h3>{department.department}</h3>
              <span>{department.status}</span>
            </div>
            <p>{department.summary}</p>
            <div className="manager-overview__metric">
              <span>{department.metric}</span>
              <strong>
                {typeof department.value_percent === "number"
                  ? `${department.value_percent}%`
                  : department.metric === "Headcount"
                    ? `${department.value} people`
                    : department.value}
              </strong>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
