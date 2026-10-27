# Report Generation Spec (for the Business Data Analyst Agent)

Add a `generate_report` capability to the existing agent. It turns verified analysis results into an editable Word report (.docx) that looks like `sample_sales_report.docx`.

Build one step at a time (Section 6). Stop after each step and show the result before starting the next. Put each piece in its own file and write a comment or docstring on every function.

## 1. What to build

- A new MCP tool, `generate_report`, on the business data server.
- A small report builder that writes a `.docx` from a structured report object.
- A chart helper that draws the revenue chart as a PNG for the report.
- A check that every number in the report comes from tool results already in the agent's state.

Do not change the existing analyses, the graph routing, or the data layer. The report is built from results the agent already has.

## 2. Rules (do not break these)

1. **The model never writes layout.** It fills the report object (Section 3). Code builds the document.
2. **Every number must come from a tool result.** This includes numbers inside the summary and finding text. Run the same evidence check the agent uses for answers. If it fails, do not build the file. Return the list of numbers that did not match.
3. **Raw values in, formatting in code.** Key figures, table cells, and chart values are stored as raw numbers plus a format name (`money`, `percent`, `integer`). Code formats them. Money in the data is in cents, so convert to the display currency in one place.
4. **Measured results and document claims stay separate.** A cause taken from a document must be worded as reported ("the management report mentions...") and never as proven.
5. **Every finding has all four parts:** finding, evidence, recommended action, caveat. If any part is missing, reject the report object.
6. **No invented content.** If a section has no data (no document evidence, for example), leave out the claim and say so in the caveat. Do not fill it with filler text.
7. **Read-only.** Reports are written only to the configured output folder (`reports/`). The model never supplies a file path.

## 3. Report object

The agent builds this JSON object from its tool results and passes it to `generate_report`. Validate it with a Pydantic model before doing anything else.

```json
{
  "title": "Monthly Sales Report",
  "period_label": "November 2024",
  "as_of_date": "2024-11-30",
  "key_figures": [
    {"label": "Revenue, Nov 2024", "value": 18420000, "format": "money", "source_ref": "call_3"},
    {"label": "Change vs October", "value": -12.0, "format": "percent", "source_ref": "call_4"},
    {"label": "Top product", "value": "Oak Dining Table", "format": "text", "source_ref": "call_5"}
  ],
  "summary": [
    "Paragraph 1: the direct answer with the main figures.",
    "Paragraph 2: what documents report, worded as reported, if any."
  ],
  "chart": {
    "title": "Monthly revenue, Jun to Nov 2024",
    "x": ["Jun", "Jul", "Aug", "Sep", "Oct", "Nov"],
    "y": [19850000, 20310000, 20780000, 21140000, 20931800, 18420000],
    "value_format": "money",
    "highlight_last": true,
    "source_ref": "call_2"
  },
  "tables": [
    {
      "title": "Top products in November",
      "columns": ["#", "Product", "Revenue", "Share"],
      "formats": ["integer", "text", "money", "percent"],
      "rows": [[1, "Oak Dining Table", 3140000, 17.0]],
      "source_ref": "call_5"
    }
  ],
  "findings": [
    {
      "finding": "Revenue fell 12.0% in November.",
      "evidence": "October R209,318 to November R184,200, down R25,118.",
      "action": "Check stock and delivery records for November before drawing conclusions.",
      "caveat": "The management report mentions supply delays. The data does not show that they caused the fall.",
      "source_refs": ["call_4"]
    }
  ],
  "notes": [
    "Revenue means quantity x unit price on completed orders only."
  ]
}
```

Limits: 3 to 5 key figures, 1 to 2 summary paragraphs, at most 2 tables, 2 to 5 findings. `source_ref` is the id of the tool call in the agent's state that produced the data.

## 4. Layout (match the sample document)

Page: A4, 1 inch margins, Arial, body about 10.5 pt. Sections in this order:

1. **Title block:** report title (large, dark blue), then a grey line with period, "Prepared by the Business Data Analyst Agent", and the as-of date, with a thin dark blue rule under it.
2. **Key figures:** one row of shaded tiles, each with a small grey label and a large bold value.
3. **Summary:** heading plus the summary paragraphs.
4. **Revenue trend:** heading plus the chart image, with alt text.
5. **Tables:** one heading and one table each. Dark blue header row with white bold text, thin light borders, numbers right-aligned.
6. **Findings and recommended actions:** a four-column table (Finding, Evidence, Recommended action, Caveat). Start this section on a new page if it would otherwise split across pages. Rows must not split across pages.
7. **Sources and notes:** bullet list in grey, listing which analyses the figures came from, then the notes.

Footer on every page: "Sample report. All figures are illustrative. Page X of Y" for sample data, or the real source note otherwise.

Colours: dark blue `1F3A5F` for headings and header rows, grey `666666` for secondary text, tile fill `EEF2F7`, table borders `D0D7E2`.

## 5. Word formatting rules (so the file stays editable)

- Use real heading styles (Heading 1) so the user can restyle or build a table of contents.
- Use real Word tables, not text with tabs. Set the width on every cell and the table, and make column widths add up to the table width.
- Shade header cells with a solid fill colour in the cell properties.
- Use a real bullet list style for notes, not typed bullet characters.
- Put a line break between paragraphs by creating separate paragraphs, never `\n` inside a run.
- Use a page number field in the footer, not typed numbers.
- Use `python-docx` for the Word file and `matplotlib` for the chart (draw to a PNG with the non-interactive `Agg` backend). Check the current `python-docx` documentation for the exact API before writing code, since table shading, cell widths, and page number fields need small XML tweaks.

## 6. Build order

Do these one at a time. Each step has a check. Do not start the next step until the check passes.

**Step 1: Report object model** (`app/reporting/models.py`)
Pydantic models for Section 3 with the limits and the "all four parts of a finding" rule.
Check: a valid object loads; objects with a missing caveat, too many findings, or an unknown format name are rejected with a clear message.

**Step 2: Formatters** (`app/reporting/formatting.py`)
`money` (cents to South African rand, displayed with `R` and thousands separators), `percent` (one decimal, signed where needed), `integer`, `text`.
Check: tests for 18420000 cents to `R184,200`, -12.04 to `-12.0%`, and rounding edge cases.

**Step 3: Chart helper** (`app/reporting/charts.py`)
Takes the chart section and writes a PNG. Bars in light blue, the last bar in dark blue when `highlight_last` is true, value labels above bars, no y-axis, no top or right border.
Check: the PNG opens and the labels match the input values.

**Step 4: Evidence validation** (`app/reporting/validate.py`)
Reuse `services/evidence_check.py`. Collect every number from the summary, findings, notes, key figures, tables, and chart, and confirm each one appears in the cited tool results (after the same rounding and formatting rules the answer check uses). Numbers that come from the report itself (years, month names, row numbers) are ignored.
Check: a report with one altered figure fails and names that figure; the valid sample passes.

**Step 5: Document builder** (`app/reporting/builder.py`)
Builds the `.docx` from a validated object following Sections 4 and 5. No LLM calls in this file.
Check: open the file in Word or convert it to PDF and compare it with `sample_sales_report.docx`: same sections, same order, tables intact, findings table not split mid-row.

**Step 6: MCP tool** (`mcp_servers/business_data_server.py`)
Add `generate_report(report: ReportObject) -> {"path": str, "warnings": [str]}`.
Flow: validate the object, run the evidence validation, build the chart, build the document, save under `reports/` with a safe generated file name, return the path. On any failure return a clear error message the agent can act on.
Check: calling the tool directly with the sample object creates a file; an invalid object returns an error and creates nothing.

**Step 7: Agent prompt and routing** (`prompts/answer_format.md`, `graph.py`)
Tell the agent when to offer a report (the user asks for a report, document, or summary file), that it must build the object only from its tool results, and what to do when the tool returns errors (fix the named figures and try again, within the existing retry cap).
Check: "Give me a report on November sales" produces a `.docx` whose figures match the ground truth.

**Step 8: Tests** (`tests/test_report_*.py`)
Cover models, formatters, validation, and builder output (open the file with `python-docx` and assert the headings, table count, and key values). Add two report questions to the evaluation set: one normal, one where the data cannot support a report and the agent must say so.

## 7. Out of scope for now

- PDF export (a Word file can be exported to PDF from Word; add a converter later if needed).
- Multiple report types. Build the monthly sales report first.
- Charts other than a single bar or line chart.
- Branding or logo support.
- Multi-user storage of reports.
