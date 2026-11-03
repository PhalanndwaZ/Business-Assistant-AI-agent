# Business glossary

All records are synthetic and generated with a fixed seed.

- **Revenue:** quantity multiplied by unit price in integer cents for each order
  item, summed across an order or reporting group.
- **Sales:** revenue from `completed` orders only. `cancelled` and `returned`
  orders are excluded from sales and revenue analyses.
- **Order date:** the ISO 8601 calendar date on which the order was placed.
- **As-of date:** 2025-01-15, used to resolve relative date questions.

December 2024 intentionally has fewer orders than November 2024 to create a
reproducible month-over-month sales dip for combined analysis examples.

`manager.json` and `admin.json` contain illustrative role-specific data for
frontend testing. They are synthetic fixtures, are not loaded by the business
analytics data store, and must not be treated as live management or account
records. The manager fixture contains department/month summaries without
person-level details. The admin fixture lists demo account metadata and the
available registration fields; user registration is handled by the
administrator-only API and stores password hashes in `data/policy/users.json`.
