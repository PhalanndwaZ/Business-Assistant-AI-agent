# Frontend Spec: Business Analyst AI (React)

Build a small React chat frontend for the existing Business Analyst AI API. A user types a question, reads the evidence-checked answer, sees the figures, sources and caveats behind it, and can keep the conversation going.

The backend already works and is not changed unless a step says so (only Step 9, and only with my approval). First read the backend's `main.py` and the README's Phase 11 section, then tell me what you found before writing anything.

## 1. How to work

- Build one step at a time (Section 7). After each step, stop, show what changed, and wait for my confirmation before the next one.
- Before writing code for a step, explain in a few sentences what you will do and why.
- One responsibility per file. Do not bundle code. Do not scaffold the whole app at once.
- Every function gets a comment (JSDoc style) saying what it does.
- Keep explanations short and practical.
- I run commands myself on Windows in PowerShell, so give me commands I can paste and tell me what I should see.

## 2. Backend contract (from the README)

Development base URL: `http://127.0.0.1:8000`. Start it from the backend project root with:

    .\.venv\Scripts\python.exe -m uvicorn main:app --reload

There is one application endpoint: `POST /ask`. Swagger UI is at `/docs` and the schema at `/openapi.json`. There is no health endpoint.

**Request**

    { "question": "Give me a report on November 2024 sales", "conversation_id": null }

Omit `conversation_id` or send `null` on the first message. The server generates a UUID and returns it. Send that UUID back on every follow-up so the server keeps the conversation context.

**Response (200)**

    { "answer": "...", "conversation_id": "uuid", "figures": [], "sources": [], "caveats": [] }

- `answer`: the final, evidence-checked text. It may contain markdown, bracketed file citations such as `[returns_policy.md]`, and quoted text from documents.
- `figures`: successful analysis and query results from the current request only.
- `sources`: tool and document names used in the current request.
- `caveats`: assumptions, evidence limits and workflow errors from the current request.
- For report requests, `answer` says whether a report file was created and includes its path (files are written to the server's `reports/` folder).

**Status codes**

| Status | Meaning |
|---|---|
| 200 | Question processed. Read `answer` and `caveats` for limits. |
| 422 | Missing, empty or whitespace-only `question`. |
| 502 | Both model providers were unavailable, or a model request was rejected. |
| 503 | Required configuration or an MCP/service dependency failed. |

There is no authentication and no rate limiting. Conversation IDs are private identifiers.

## 3. Gaps in the contract (handle these deliberately)

1. **CORS.** The README does not mention it. A browser app on `localhost:5173` calling `localhost:8000` will be blocked. Use the Vite dev proxy (`/api` forwards to the backend, with the prefix removed) so the backend stays unchanged. If this is deployed later, the backend needs CORS middleware with an explicit allowed origin.
2. **Unknown shapes.** The README shows `figures`, `sources` and `caveats` as empty arrays, so the shape of their entries is not documented. Do not guess. Step 0 captures real responses and the types come from those. Anything unrecognised is shown in a generic fallback view.
3. **No report download.** The API returns a file path only. The UI shows the path with a copy button. A real download needs a new backend endpoint (Step 9).
4. **No history endpoint.** The server remembers context, but the browser cannot fetch past messages. The UI keeps its own copy of the displayed messages in `localStorage`, keyed by conversation ID. If that is cleared, the conversation still continues on the server but the old messages are no longer shown.
5. **Slow responses.** One answer can take many seconds (model calls, up to 8 tool steps, provider retries). Show progress, allow cancelling, and use a generous timeout (starting value 120 seconds, set in `config.js`).
6. **Error body shapes.** FastAPI returns `{"detail": ...}`. For 422, `detail` is a list. Handle a string, a list, or a missing body.
7. **No documented question length limit.** Use a soft limit of 1000 characters in the UI (constant in `config.js`) and confirm the real limit with me.

## 4. Stack and structure

- React with Vite, plain JavaScript (not TypeScript), React hooks only. No Redux and no router (one page).
- `react-markdown` for answer text. Plain CSS with CSS variables, light and dark through `prefers-color-scheme`.
- Check the current Vite and `react-markdown` documentation before installing or configuring them.
- The frontend talks only to this API. It never calls the model providers and holds no API keys.

Folder, created inside a new `frontend/` directory next to the backend:

    frontend/
      index.html
      vite.config.js            dev proxy: /api -> http://127.0.0.1:8000
      .env.example              VITE_API_BASE=/api, VITE_USE_MOCK=false
      mock/fixtures/            real saved responses (Step 0)
      src/
        main.jsx
        App.jsx
        config.js               API base, timeout, question limit, example questions
        api/
          client.js             askQuestion(), error normalisation
          errors.js             status code -> friendly message
          mockClient.js         canned responses for offline work
        hooks/
          useConversation.js    messages, conversation id, loading, error, send, cancel, reset
          useElapsedTime.js
        storage/
          conversationStore.js  localStorage read/write, wrapped in try/catch
        components/
          ChatWindow.jsx
          MessageList.jsx
          UserMessage.jsx
          AssistantMessage.jsx
          AnswerText.jsx        safe markdown
          EvidencePanel.jsx
          CaveatList.jsx
          SourceChips.jsx
          FiguresView.jsx
          ReportNotice.jsx
          QuestionInput.jsx
          ExampleQuestions.jsx
          LoadingIndicator.jsx
          ErrorBanner.jsx
          SyntheticDataNotice.jsx
        styles/
          tokens.css
          app.css

## 5. UI behaviour

- **Layout:** header with the app name and a "New conversation" button, a scrolling message area, and the input fixed at the bottom. A small footer note says all data and documents are synthetic.
- **Empty state:** a short intro and three example questions the user can click to send:
  - How did completed-order revenue change from November to December 2024?
  - What is the reporting window for a damaged product?
  - What changed in December revenue, and what factors did management report?
- **Messages:** user messages on the right, assistant messages on the left.
- **Evidence under each assistant answer:** caveats first and visible (amber), then source chips, then figures collapsed by default. Caveats come first because this project relies on them to stop overclaiming. Do not render a section that has no entries.
- **Input:** Enter sends, Shift+Enter adds a new line. The question is trimmed. Sending is disabled while the box is empty or a request is running. Show a character count near the limit.
- **Loading:** show "Analysing... 12s" with a Cancel button. Cancelling aborts the request and shows a short "Cancelled" note.
- **Errors:** shown in the message list, never saved as an assistant answer, each with a Retry button:
  - 422: "Please enter a question."
  - 502: "The AI model providers are unavailable right now. Try again in a moment."
  - 503: "A required service isn't available. Check that the backend is running and configured."
  - Network failure: "Can't reach the API. Is the backend running?"
  - Anything else: a generic message with no raw body.
- **New conversation:** clears the conversation ID and the stored messages.
- **Accessibility:** labelled input, new answers announced politely to screen readers, focus returns to the input after an answer, everything usable with the keyboard, readable contrast in both themes.
- **Responsive:** usable at phone width, no horizontal page scroll.

## 6. Rules

1. **Display, do not compute.** The UI never recalculates, rounds or reinterprets figures. Money in tool results can be integer cents. Do not convert it unless a field is clearly marked as cents, do it in one documented helper, and keep the original value visible. Confirm against real data first.
2. **Answers are untrusted text.** They can contain quoted document text. Render markdown without raw HTML, never use `dangerouslySetInnerHTML`, open links with `rel="noopener noreferrer"`, and never open a link automatically.
3. **Conversation IDs are private.** Keep them in `localStorage` only. Do not put them in the URL, console logs or analytics.
4. **One request at a time** per conversation. Ignore a send while one is running.
5. **No raw errors or stack traces** shown to the user. Log details to the console in development only.
6. **Storage can fail.** Wrap every `localStorage` read and write in try/catch and keep working in memory if it throws.
7. **Empty is normal.** `figures`, `sources` and `caveats` can all be empty.
8. **Do not change the backend** except in Step 9, which needs my approval first.

## 7. Build steps

**Step 0: Look before building**
Read `main.py` and confirm the request and response models. With the backend running, send these through Swagger UI and save each real response as a JSON file in `mock/fixtures/`: a structured question, a document question, a combined question, an unanswerable question, a report request, and a follow-up in the same conversation. Also save a 422 response. Show me the real shapes of `figures`, `sources` and `caveats`, and how a report path appears inside `answer`.
Check: the fixtures exist and I have seen the real shapes.

**Step 1: Project setup**
Create the Vite React app in `frontend/`, configure the dev proxy, add `.env.example` and `config.js`.
Check: `npm install` then `npm run dev` starts the app, and a request to `/api/openapi.json` in the browser returns the backend schema through the proxy.

**Step 2: API client**
`client.js` sends `POST /ask` with the question and the optional conversation ID, supports cancelling through an abort signal, applies the timeout, and returns a clean result or a normalised error. `errors.js` maps statuses and network failures to the messages in Section 5.
Check: a real question returns an answer and a conversation ID. An empty question returns the 422 message. Stopping the backend gives the "Can't reach the API" message.

**Step 3: Mock client**
`mockClient.js` returns the saved fixtures, switched by `VITE_USE_MOCK`, so I can build the interface without using model quota.
Check: with the mock on, each fixture can be returned and the real API is not called.

**Step 4: Conversation state**
`useConversation.js` and `conversationStore.js`: messages, conversation ID, loading, error, send, cancel and reset, with persistence in `localStorage` as described in Section 3.
Check: the conversation ID is reused on follow-ups, survives a page refresh together with the displayed messages, and is cleared by a new conversation.

**Step 5: Chat shell**
`App.jsx`, `ChatWindow.jsx`, `MessageList.jsx`, `UserMessage.jsx`, `QuestionInput.jsx`, `ExampleQuestions.jsx`, `SyntheticDataNotice.jsx`, and the base styles. Plain text answers for now.
Check: I can ask a question, see my message and a plain answer, click an example question, and use Enter and Shift+Enter.

**Step 6: Answer rendering**
`AnswerText.jsx` with safe markdown. Bracketed citations like `[returns_policy.md]` stay readable.
Check: bold text, lists and quotes render, and a test answer containing HTML tags shows them as text and runs nothing.

**Step 7: Evidence panel**
`EvidencePanel.jsx`, `CaveatList.jsx`, `SourceChips.jsx`, `FiguresView.jsx`, built from the real shapes found in Step 0, with a generic fallback view for anything unrecognised.
Check: the structured, document and combined fixtures each show the right sections, and the unanswerable fixture shows its caveats clearly.

**Step 8: Loading, cancel and errors**
`LoadingIndicator.jsx`, `useElapsedTime.js`, `ErrorBanner.jsx`, with Retry and Cancel.
Check: a slow request shows the elapsed time and can be cancelled. Each error type shows the right message, and Retry resends the last question once.

**Step 9: Report files (ask me first, this changes the backend)**
`ReportNotice.jsx` detects the report path in the answer, shows the file name and a copy button, and nothing else. Then propose to me, without building it, a safe download endpoint such as `GET /reports/{filename}` that only serves `.docx` files that resolve inside the `reports/` folder and rejects any path traversal. Also propose adding a structured field (for example `report_filename`) to the response, so the UI does not depend on reading a path out of the answer text.
Check: the path and copy button appear for the report fixture. Do not touch the backend until I approve.

**Step 10: Polish and handover**
Responsive layout, accessibility pass, light and dark themes, and a short `frontend/README.md` with the two commands to run backend and frontend together.
Check: usable at phone width, fully keyboard-operable, and a new person can run both from the README.

## 8. Out of scope for now

Login or multiple users, streaming responses, charts, editing or deleting past messages, exporting conversations, deployment, translations, and automated frontend tests.

## 9. Done when

I can run the backend and the frontend, ask a structured, a document and a combined question, see each answer with its caveats, sources and figures, continue the conversation, cancel a slow request, recover from every error type, start a new conversation, and refresh the page without losing the displayed messages.
