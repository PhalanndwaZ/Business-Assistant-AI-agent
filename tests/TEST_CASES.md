# Test cases and design decisions

## Run tests

Activate the project virtual environment, then run:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\run_tests.py
```

The runner uses the current Python interpreter, runs offline deterministic
tests, and does not require Groq or Mistral credentials. It creates:

- `evaluation/reports/all-report.md`: readable case-by-case outcome and failure
  details.
- `evaluation/reports/all-junit.xml`: JUnit XML for editor and CI integration.

Run only one area with `python scripts\run_tests.py --suite data`,
`python scripts\run_tests.py --suite rag`, or
`python scripts\run_tests.py --suite workflow`. Add `--verbose` to show each
pytest case while it runs. The report files are generated output and are
ignored by git.

To ask a live question after configuring the Groq key in `.env`, run:

```powershell
.\.venv\Scripts\python.exe -m app.cli "Which product generated the highest sales last month?"
```

To run the five-question Phase 5 CLI acceptance check, run:

```powershell
.\.venv\Scripts\python.exe scripts\phase5_cli_smoke.py
```

This makes five live Groq-backed CLI requests, spaces them by 65 seconds to
reduce token-per-minute rate-limit failures, and writes the answers and
pass/fail checks to `evaluation/reports/phase5-cli-smoke.md`. It also writes
one JSONL trace record per question to
`evaluation/reports/phase5-cli-trace.jsonl`, including model drafts, tool
arguments, raw and parsed tool results, and evidence verdicts with the
compared numeric candidates. Run a single case with `--case 3` to debug Q3
without repeating all five requests. The script compares results with figures
calculated from the local configured dataset; it is not part of the offline
pytest suite.

To ingest all manifest-listed documents with the configured Mistral embedding
model, run:

```powershell
.\.venv\Scripts\python.exe -m app.rag.ingest
```

This makes live embedding API requests and writes metadata and vectors to
`data/vector_store/chunks.json`. Re-running ingestion replaces existing chunks
for each document rather than duplicating them. The offline tests use a fake
embedder to verify chunk metadata, retries, batching, and idempotency without
calling Mistral.

To repeat the live similarity-threshold calibration, run:

```powershell
.\.venv\Scripts\python.exe scripts\calibrate_retrieval.py
```

This embeds a fixed set of answerable and unanswerable questions with Mistral,
prints the top chunk scores and accepted documents, and fails if expected
documents are missed or an unanswerable case returns a result. The calibrated
cutoff and observed scores are recorded in the root `README.md`.

## Detailed deterministic test-case matrix

These cases verify the implemented configuration, JSON, Pandas, MCP tool
functions, ingestion helpers, vector store, retriever, and LangGraph graph.
Workflow tests use a deterministic fake model and actual local MCP stdio
servers; they do not require paid API calls. A live Groq-backed CLI run and
real Mistral ingestion/threshold calibration still require credentials.

| ID | Area | Scenario and input | Expected result | Design decision being protected | Test |
|---|---|---|---|---|---|
| CFG-01 | Configuration | Load settings without either API key | A clear `ConfigurationError` names missing keys | Secrets come from environment variables and startup fails clearly | `test_load_settings_requires_both_api_keys` |
| CFG-02 | Configuration | Load settings with keys but no optional overrides | Stable defaults and absolute project paths | Centralized config and fixed as-of date | `test_load_settings_resolves_defaults_and_paths` |
| CFG-03 | Configuration | Set similarity threshold above 1 | Reject invalid value | Similarity is a bounded cosine score | `test_load_settings_rejects_invalid_similarity` |
| DATA-01 | Generation | Generate records twice with the same seed | Identical records | Seeded fixture data is reproducible | `test_generate_records_is_reproducible` |
| DATA-02 | Generation | Compare December and November order counts | December is lower | Dataset contains a repeatable dip for combined questions | `test_generated_data_has_a_december_sales_dip` |
| DATA-03 | Loader | Remove required `customer_id` | Reject dataset with row and field context | Required schemas are validated at load time | `test_loader_rejects_missing_fields` |
| DATA-04 | Loader | Replace an ISO date with invalid text | Reject dataset before analysis | Dates are parsed and validated, not silently coerced | `test_loader_rejects_invalid_dates` |
| DATA-05 | Loader | Point an order at a nonexistent customer | Reject broken foreign key | Referential integrity is checked during startup | `test_loader_rejects_broken_references` |
| DATA-06 | Loader | Request an unapproved dataset | Reject request | Dataset names come from a fixed allowlist, never caller paths | `test_loader_rejects_unapproved_dataset` |
| ANALYSIS-01 | Revenue | November product revenue compared to an independent Pandas calculation | Top product and cents match | Pandas is authoritative for arithmetic; money stays in integer cents | `test_revenue_by_product_matches_independent_calculation` |
| ANALYSIS-02 | Revenue | Aggregate yearly revenue by category | Every total is integer cents | Shared revenue definition avoids floating-point currency | `test_revenue_by_category_returns_integer_cents` |
| ANALYSIS-03 | Time series | Aggregate January–December at month granularity | Keys are complete and sorted `YYYY-MM` values | Named analyses constrain grouping to supported granularities | `test_revenue_by_period_supports_month_granularity` |
| ANALYSIS-04 | Comparison | Compare November 2024 with an empty November 2023 period | Prior value is zero and percent change is `null` | Zero-baseline changes are explicitly undefined, not crashes or infinity | `test_period_change_handles_zero_previous_value` |
| ANALYSIS-05 | Empty result | Query a valid period with no records | Return an empty result collection | Empty periods are normal results, not errors | `test_empty_period_returns_an_empty_result` |
| ANALYSIS-06 | Ranking | Request the top three customers | Return at most three ranked rows with revenue | Ranking is deterministic and capped by the requested `top_n` | `test_top_customers_has_limit_and_revenue` |
| ANALYSIS-07 | Statistics | Calculate trend and deviation-based outliers | Include direction, slope/period values, and method assumptions | Statistical summaries expose their method and caveats | `test_trend_and_outliers_include_metric_assumptions` |
| ANALYSIS-08 | Dispatch | Add a file path parameter to an analysis call | Reject unknown parameter before execution | Models select named analyses and cannot inject code or paths | `test_run_analysis_rejects_unknown_parameters` |
| EVIDENCE-01 | Numeric grounding | Format 5000 revenue cents as `$50.00` | Accept exact currency-format conversion | Money values stay associated with their field and unit | `test_revenue_cents_can_be_formatted_as_dollars` |
| EVIDENCE-02 | Numeric grounding | Claim 50 cents when only an order count equals 50 | Reject the claim | Matching digits alone do not prove a metric or unit | `test_order_count_cannot_support_revenue_in_cents` |
| EVIDENCE-03 | Numeric grounding | Claim 5% when the only 5 is an order count | Reject the claim | Percentages need percentage evidence, not an unrelated number | `test_count_cannot_support_percentage_claim` |
| EVIDENCE-04 | Numeric grounding | Claim 12.5% with a `percent_change` result of 12.5 | Accept the claim | Matching percentage evidence supports formatted numeric claims | `test_matching_percentage_field_supports_percentage_claim` |
| EVIDENCE-05 | Numeric grounding | Claim $50 revenue when the result only contains a $50 unit price | Reject the claim | Unit prices and aggregate revenue are separate metrics | `test_unit_price_cannot_support_total_revenue_claim` |
| EVIDENCE-06 | Numeric grounding | Claim cost when matching amount appears only as revenue | Reject the claim | Revenue cannot be relabeled as cost | `test_revenue_cannot_support_cost_claim` |
| EVIDENCE-07 | Numeric grounding | Explain a revenue period change returned as generic comparison fields | Accept cents and percentage supported by sibling metric context | Analysis metric and units remain attached to result values | `test_period_change_uses_sibling_metric_context` |
| EVIDENCE-08 | Numeric grounding | State supported revenue then repeat its value as unsupported cost | Reject the second claim only | Each figure is matched to its local metric wording | `test_metric_context_is_scoped_to_each_number` |
| EVIDENCE-09 | Numeric grounding | Check period-comparison totals and percentage with Unicode minus/spacing | Accept the tool-grounded cents and signed percentage; ignore date punctuation and conversion constants | Numeric claims retain their metric, sign, and unit across formatted answers | `test_period_revenue_and_percent_change_keep_their_own_metrics`, `test_unicode_minus_and_escaped_percent_match_percentage_evidence`, `test_date_followed_by_comma_is_not_parsed_as_count` |
| EVIDENCE-10 | Numeric grounding | Repeat a `revenue_cents` field and describe cents-to-dollars conversion | Accept the grounded amount and ignore the divide-by-100 constant | Explanatory conversions do not become unsupported business claims | `test_revenue_cents_field_reference_and_conversion_constant_are_valid` |
| EVIDENCE-11 | Document grounding | Attribute a claim to a retrieved document with a matching exact quote, or give an uncited response despite retrieved context | Accept only the matching source name and passage; reject uncited acknowledgements | Document claims require traceable retrieved evidence and the model must answer from available passages | `test_document_claim_requires_matching_source_and_exact_quote`, `test_answer_without_a_document_citation_is_rejected_when_passage_exists` |
| EVIDENCE-12 | Document grounding | Cite an unreturned filename or provide an unsupported quote | Reject the document claim | Citations cannot be fabricated or detached from retrieved content | `test_document_claim_rejects_a_source_not_in_retrieved_chunks`, `test_document_claim_requires_an_exact_quote_from_the_cited_chunk` |
| EVIDENCE-13 | Causal claims | State a direct cause versus an attributed, explicitly uncertain report factor | Reject proven causation; accept properly qualified reporting | Reported factors are not proof of causation | `test_causal_claim_must_be_attributed_and_uncertain` |
| EVIDENCE-14 | Document numerics | State a number with a nearby unit present in retrieved passage text | Accept the number with its local count context | Document figures retain their units during evidence checking | `test_document_text_supports_a_number_with_its_local_unit` |
| TOOL-01 | Schema | Ask for tool schema | Return only approved datasets, analyses, relationships, and glossary | Tool descriptions publish the constrained business interface | `test_schema_exposes_allowlisted_datasets_and_analyses` |
| TOOL-02 | Query | Filter completed orders and request three rows | Return requested columns, at most three rows, and total match count | Query output is capped without hiding the number of matches | `test_query_business_data_caps_rows_and_returns_total` |
| TOOL-03 | Query | Request a `password` field | Reject unapproved field | Tool calls cannot inspect unapproved columns | `test_query_business_data_rejects_unknown_fields` |
| TOOL-04 | Query | Use a `regex` filter operator | Reject unsupported operator | Filters are declarative and strictly allowlisted | `test_query_business_data_rejects_unknown_operators` |
| TOOL-05 | Query | Date-filter `order_items` for January | Every result's parent order is dated in January | Child records inherit date filtering through their order, not a guessed item date | `test_query_business_data_filters_items_by_related_order_date` |
| RAG-01 | Chunking | Split text longer than configured chunk size | Chunks respect size and overlap exactly | Chunking uses explicit 800-character/100-character parameters | `test_split_text_uses_configured_overlap` |
| RAG-02 | Metadata | Create a chunk using manifest metadata | Stable ID, type, and optional page are retained | Citations derive from document metadata, not model-generated guesses | `test_document_chunks_preserve_manifest_metadata` |
| RAG-03 | Phase 6 documents | Load the sample manifest and validate every listed document | Each document is readable, labelled synthetic, and has a valid type/date; policy, reports, notes, and injection test are present | RAG examples are clearly marked synthetic, provenance is explicit, and test injection remains untrusted content | `test_phase_six_sample_documents_are_synthetic_and_fully_manifested` |
| RAG-04 | Input safety | Put `../outside.md` in manifest | Reject before reading the outside file | Manifest paths are confined to the configured document directory | `test_manifest_rejects_paths_outside_documents_directory` |
| RAG-05 | Idempotency | Replace chunks for an already-ingested document | Store contains one current copy | Re-ingestion must not accumulate duplicate chunks | `test_vector_store_replaces_document_chunks_without_duplicates` |
| RAG-06 | Model consistency | Write chunks from a different embedding model | Reject mixed model store | Index/query vectors must use the same embedding model | `test_vector_store_rejects_mixed_embedding_models` |
| RAG-07 | Vector validation | Load a vector containing `NaN` | Reject invalid vector | Non-finite values cannot bypass relevance checks | `test_vector_store_rejects_non_finite_embedding_values` |
| RAG-08 | Reconciliation | Remove a document from the manifest | Its old chunks are pruned, current ones remain | Search results must reflect the current manifest | `test_vector_store_prunes_documents_removed_from_manifest` |
| RAG-09 | Embedding batches | Embed more than one configured batch of texts | Requests are bounded and every input receives one vector | API requests stay within the batch limit while preserving input order | `test_embed_splits_requests_into_bounded_batches` |
| RAG-10 | Embedding retry | Return HTTP 429, then a successful embedding response | Retry with exponential backoff and return vectors | Rate limits are retried without hiding permanent client errors | `test_embed_retries_rate_limits_with_exponential_backoff`, `test_embed_does_not_retry_client_errors` |
| RAG-11 | Embedding validation | Return a vector with the wrong dimensions | Reject the response before persisting it | All documents and query vectors must share the configured dimensions | `test_embed_rejects_mismatched_response_dimensions` |
| RAG-12 | End-to-end ingestion | Ingest a manifest twice with a deterministic fake embedder | Persist all chunk fields and metadata, with no duplicate IDs | Re-ingestion replaces document chunks and keeps file-level model metadata | `test_ingestion_embeds_all_manifest_documents_idempotently` |
| RAG-13 | Similarity cutoff | Rank one exact match and one passage scoring below the configured cutoff | Keep the exact match and reject the below-cutoff passage | The live-calibrated `MIN_SIMILARITY` is applied consistently | `test_search_applies_calibrated_similarity_threshold` |
| RAG-14 | Metadata filtering | Search for a specific document date | Return only documents matching that exact date | Optional date filters are applied before similarity ranking | `test_search_filters_by_document_date` |
| RAG-15 | Live calibration | Embed three answerable and three unanswerable sample questions | Preserve the expected document for answerable questions and return no chunks for unanswerable ones | Similarity cutoff is selected from observed corpus scores rather than guessed | `scripts/calibrate_retrieval.py` |
| SEARCH-01 | Ranking | Query against an exact vector and a filtered-out orthogonal vector | Return the matching chunk and source metadata | Cosine ranking and metadata filters are applied before returning passages | `test_search_ranks_cosine_matches_and_applies_filters` |
| SEARCH-02 | Threshold | Query against an unrelated orthogonal vector | Return explicit no-results response | Weak matches are dropped rather than presented as evidence | `test_search_returns_explicit_no_results_below_threshold` |
| SEARCH-03 | Limits | Supply a fractional `k` | Reject invalid result limit | Caller cannot bypass bounded top-k behavior | `test_search_rejects_invalid_k` |
| SEARCH-04 | Consistency | Open a store with a different embedding model | Refuse retriever startup | Model mismatch is detected before serving queries | `test_retriever_refuses_embedding_model_mismatch` |
| TEST-01 | Reporting | Convert JUnit results containing pass, failure, and skip | Markdown counts each outcome and includes failure text | Human-readable reports must preserve actionable test failures | `test_report_lists_pass_skip_and_failure_details` |
| TEST-02 | Reporting | Simulate pytest failing before producing new XML when an old report exists | Do not publish a report from the earlier run | Report outputs must describe this run, not stale results | `test_failed_pytest_start_does_not_report_stale_junit` |
| GRAPH-01 | Workflow | Ask for category revenue; fake analysis returns 12345 cents | Answer reports only that supported number and names its source | LLM explains; Pandas/MCP provides figures | `test_question_uses_tool_and_returns_numeric_supported_answer` |
| GRAPH-02 | Evidence | Draft 7654 when tool result only contains 4321 | Reject first draft, retry, and accept supported number | Deterministic evidence check gates numeric answers | `test_unsupported_number_is_rejected_and_retried` |
| GRAPH-03 | Tool recovery | First MCP call errors; second call is valid | Feed tool error back to agent and retain both outcomes | Correctable tool failures may be retried within bounded retries | `test_failed_tool_call_can_be_corrected_by_agent` |
| GRAPH-04 | Clarification | Ask an ambiguous question and return clarification action | Ask one clarification, make no MCP calls, and stop | Each question is independent; ambiguity is not guessed | `test_clarification_action_ends_without_calling_data_tools` |
| GRAPH-05 | Loop protection | Repeatedly request tools with a one-call cap | Stop after one MCP call and add a cap caveat | LangGraph has a hard step limit against runaway loops | `test_step_cap_stops_repeated_tool_requests` |
| GRAPH-06 | Unsupported answer | Tool call fails and model invents a number | Replace it with an explicit cannot-answer response | No successful tool output means no numerical answer | `test_no_successful_tool_result_forces_cannot_answer` |
| GRAPH-07 | Reliability | Model raises transient failures twice | Retry with delays of 1 and 2 seconds, then return success | Model API retries use exponential backoff | `test_model_api_uses_exponential_backoff` |
| GRAPH-08 | MCP transport | Start local business and document servers via stdio and invoke both | Discover both tool sets and route each call to its server | Local MCP transports isolate tools from direct file access | `test_analyst_mcp_client_routes_both_servers_over_stdio` |
| GRAPH-09 | Conversation state | Invoke agent after a tool result and an evidence rejection | Preserve system prompt, original question, assistant tool call, and result | LangGraph message history must preserve tool-call protocol context | `test_unsupported_number_is_rejected_and_retried` |
| GRAPH-10 | Evidence fail-closed | Keep an unsupported number after the retry cap | Do not return that number as factual | Evidence retries cannot degrade into caveated unsupported claims | `test_exhausted_evidence_retry_does_not_return_unsupported_number` |
| GRAPH-11 | MCP errors | Raise a JSON-RPC `McpError` while calling a tool | Record a failed tool result and return cannot-answer response | Protocol errors are visible and handled at the tool boundary | `test_mcp_protocol_error_is_recorded_and_finalized` |
| GRAPH-12 | MCP cleanup | Fail the session initialization handshake | Close both MCP session and stdio transport before re-raising | Child processes/resources must not leak when startup fails | `test_mcp_client_closes_transport_if_initialization_fails` |
| GRAPH-13 | CLI acceptance | Ask five fixed structured-data questions through the CLI | Check returned entities, figures, and source attribution against local analysis results | Phase 5 must verify representative end-to-end CLI answers, not just help output | `scripts/phase5_cli_smoke.py` |
| GRAPH-14 | CLI acceptance check | Give the smoke checker an answer with the expected entity, number, and source; then omit evidence | Accept grounded answers and identify missing numbers or sources | Acceptance-check logic must fail visibly when the CLI output is incomplete | `test_answer_check_accepts_grounded_values_and_cited_source`, `test_answer_check_rejects_missing_number_or_source` |
| GRAPH-15 | CLI acceptance check | Return expected text and negative percentages with Unicode spacing/signs | Match normalized entity text and preserve the numeric sign | Model formatting does not create false acceptance failures | `test_answer_check_normalizes_nonbreaking_spaces_in_expected_text`, `test_answer_number_parser_preserves_unicode_negative_percentages` |
| GRAPH-16 | Document-only | Ask a policy question using a retrieved passage | Cite the exact document and quote its supporting text | Answers use retrieved chunks and preserve source metadata | `test_document_only_answer_requires_retrieved_source_and_quote` |
| GRAPH-17 | Combined | Ask for an analysis figure and management's reported explanation | Use both servers, keep the figure and reported factor distinct, and qualify causation | Measured changes and possible document explanations are different evidence types | `test_combined_answer_keeps_analysis_numbers_and_reported_factors_separate` |
| GRAPH-18 | Injection resistance | Retrieve a note containing a planted instruction | Treat the instruction as untrusted content and do not follow it | Retrieved text is data, never agent instructions | `test_planted_document_instruction_is_treated_as_untrusted_data` |
| GRAPH-19 | Unanswerable | Ask an unrelated question with no relevant retrieved passages | State that the available sources cannot answer | Similarity rejection leads to an honest limitation | `test_unrelated_question_with_no_retrieved_passages_is_not_answered` |
| GRAPH-20 | Evidence fallback | Keep an unsupported combined answer after the retry cap | Omit the draft and show the verbatim period-change result plus exact, question-relevant retrieved sentences | Evidence failures do not discard verified figures/passages or return unsupported claims | `test_invalid_document_draft_falls_back_to_exact_retrieved_excerpt` |
| GRAPH-21 | Model rate limit | Receive transient model rate-limit errors before a successful response | Retry with longer waits of 8 and 16 seconds | Token-per-minute limits need enough backoff to recover | `test_model_rate_limit_uses_longer_backoff` |

## Important limits and next tests

- Unit tests use fixed vectors and synthetic records; they do not claim that a
  particular similarity threshold is empirically calibrated.
- The complete five-question live CLI sequence requires Groq credentials and
  has not been run as a single paced sequence. Cases 3, 4, and 5 have each been
  run individually; deterministic workflow tests cover graph routing, tool
  selection, retries, and numeric evidence handling.
- Phase 10 now has a 31-question bank and independent Pandas ground truth.
  Run `.\.venv\Scripts\python.exe -m evaluation.evaluate` to verify the
  question contracts and produce `evaluation/reports/phase10-evaluation.md`.
  This offline readiness report does not score live agent answers.
- Run `.\.venv\Scripts\python.exe -m evaluation.evaluate --live` to exercise
  the whole bank against Groq and both MCP servers. Add `--deep-eval` for
  DeepEval faithfulness, answer relevancy, context precision, and context
  recall signals. These modes make API requests and have not been run as part
  of offline validation.
- Review `all-report.md` and JUnit XML after each run. A passing unit suite is
  evidence for these cases only, not proof that answers are correct in
  production.

## Phase 10 evaluation cases

The question bank is `evaluation/questions.py`. It has 12 structured-data
questions, 7 document questions, 4 combined questions, 4 unanswerable
questions, and 4 safety/injection questions. Each case records required tools,
expected analysis or dataset arguments, source documents, and refusal or
causality criteria where applicable. `evaluation/expected_answers.py`
computes all structured and combined ground truth from raw JSON using its own
Pandas joins and aggregations.

The live grader compares tool arguments and returned data with that
independent truth, then checks answer facts, citations, evidence-check
verdicts, unanswerable refusals, safety behavior, and causal claims. Group
rates and individual failure causes are written to the Phase 10 report.
Deterministic tests cover the case inventory, source fixtures, ground truth,
tool-argument grading, and the December order dip; they do not make model or
embedding API calls.

## Phase 11 HTTP API

Start the API with `.\.venv\Scripts\python.exe -m uvicorn main:app --reload`
and send JSON containing `question` to `POST /ask`. The response includes the
same final graph answer as the CLI, along with tool-backed figures, source
names, and evidence caveats. Input validation returns HTTP 422; configuration
and MCP failures return HTTP 503; model-provider failures return HTTP 502.
Authentication and rate limiting are not included.

`tests/test_api.py` verifies the response contract, blank-input validation,
configuration-error response, and no-invented-figures behavior.
