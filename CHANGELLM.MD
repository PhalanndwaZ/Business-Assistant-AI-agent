# Task: Use Inception Labs as the primary LLM, with Groq as the automatic fallback

## Context
The project is the Business Data Analyst Agent (LangGraph + MCP + Pandas + RAG). It currently calls a Groq-hosted model. Change it so every LLM call goes to Inception Labs first, and falls back to Groq when Inception is unavailable. Do not change the graph routing, the MCP tools, the analyses, the evidence check, or the report builder.

First read the existing code that creates and calls the LLM (config.py, graph.py, anywhere the Groq client is built) and tell me how it works today before proposing changes. Adapt to what is really there; do not assume.

## How to work (important)
- Build one step at a time. After each step, stop, show what changed, and wait for me to confirm before the next step.
- Before writing code for a step, explain in a few sentences what you will do and why.
- One responsibility per file. Put every new piece in its own file.
- Every function gets a comment or docstring saying what it does.
- Keep explanations short and practical. Do not hand me the whole feature at once.

## Provider facts (verified from Inception's docs; re-check the model name on their Models page)
- Inception's API is OpenAI-compatible. Base URL: https://api.inceptionlabs.ai/v1
- Default model: mercury-2 (recommended for chat and agent tool calls). mercury-3 also exists.
- API key variable: INCEPTION_API_KEY, sent as a Bearer token.
- Tool/function calling is supported.
- Error codes: 429 means back off and retry. 500, 502, 503, 504 are temporary (503 = engine overloaded). 400 = bad request, including context_length_exceeded. 401 = bad key. 402 = billing inactive or quota exceeded. 404 = model not found. Errors return JSON with an error object (message, type, param, code).

## Behaviour rules
1. Every LLM call tries Inception first, then Groq. Tools must be bound to BOTH models, because each needs the tool schemas.
2. Fall back when Inception returns 429 (after its retries), 500/502/503/504, times out, or the connection fails.
3. Also fall back on 401, 402 and 404, but log these at ERROR level once, because they are configuration or billing problems, not temporary outages.
4. Do NOT fall back on 400. That is a bug in our request, so surface it. Do not retry the same bad request on another provider.
5. Keep retries on the primary small, so the fallback starts quickly: starting values of 2 retries with exponential backoff and jitter, and a total time budget of about 20 seconds per call. Put all of these in config.
6. Fallback happens per LLM call, not per user question. The next call tries Inception again.
7. Record which provider and model produced every LLM response (in graph state and in the logs). I need this to report evaluation results per provider.
8. If both providers fail, return the project's existing clear error (no traceback, no keys, no file paths).
9. Never log or return API keys. Update .env.example with variable names only.
10. Startup check: if INCEPTION_API_KEY is missing, run Groq-only and log a warning. If both keys are missing, fail with a clear message.

## Steps

### Step 1: Configuration
Add to config.py: INCEPTION_API_KEY, INCEPTION_BASE_URL, INCEPTION_MODEL (default mercury-2), the existing Groq settings, retry count, backoff settings and the per-call time budget. Read keys from environment only.
Check: the app starts with both keys, with only Groq, and with neither (clear failure).

### Step 2: Inception client
New file for building the Inception chat client through its OpenAI-compatible endpoint. Use the library the project already uses for LLM calls. Check the current docs for that library before writing code.
Check: a plain question works through Inception alone.

### Step 3: Tool calling through Inception
Bind the existing tools to the Inception client and run the existing 5-question structured check.
Check: tool calls are produced and executed. Record which of the 5 pass. Do not fix anything yet; just report.

### Step 4: Fallback wrapper
New file that combines the two clients using the rules above, with the error classification in its own small function.
Check, by forcing each failure on purpose (wrong key, wrong base URL, blocked network, bad model name): 401, 404 and connection errors fall back and log correctly; a deliberately malformed request does not fall back; if Groq is also broken, the user gets the clear error.

### Step 5: Wire it into the graph
Replace the single Groq call with the wrapper. Add the provider and model to state and logs.
Check: the 5 questions pass through the full graph, and the logs show which provider answered each call.

### Step 6: Compare providers
Run the same 5 questions on Inception only, then Groq only. Give me a small table of pass/fail per question per provider, and list any differences in tool-call behaviour.
Check: results are recorded so my evaluation report can name the provider.

### Step 7 (optional, ask me first): circuit breaker
If Inception fails several times in a row, skip it for a cooldown period instead of retrying on every call, then try it again.
Check: after repeated forced failures, calls go straight to Groq, and Inception is retried after the cooldown.

## Out of scope
Streaming, cost tracking, load balancing between providers, changing prompts or tool descriptions, and adding more providers.

## Done when
Inception answers by default, Groq takes over cleanly on the failure types above, the answer's provider is visible in logs and state, and the 5-question check passes through the full graph.