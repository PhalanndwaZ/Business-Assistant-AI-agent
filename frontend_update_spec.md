# Frontend Update Spec: Login, Roles, Charts and Moderation Notices

This extends the React frontend that already exists (see `frontend_spec.md`). Do not rebuild what is there. Change only what this spec names.

The backend changes behind it are described in `update_spec.md`: login and roles, a moderation layer, charts, and a sales decline risk report. Read the current frontend code and both specs first, then tell me what you found before changing anything.

## 1. How to work

- Build one step at a time (Section 6). After each step, stop, show what changed, and wait for my confirmation.
- Before writing code for a step, explain in a few sentences what you will do and why.
- One responsibility per file. Do not bundle code or scaffold everything at once.
- Every function gets a comment (JSDoc style) saying what it does.
- Keep explanations short and practical.
- I run commands myself on Windows in PowerShell, so give me commands I can paste.
- Check the current documentation for the chart library before installing it. Its API changes.

## 2. What the frontend now depends on

These come from `update_spec.md`. Anything marked **assumed** is not defined there. Step U0 confirms it against the real backend.

| Piece | What the frontend needs |
|---|---|
| `POST /auth/login` | Username and password in, a signed token out. Response shape and token expiry are **assumed**. |
| `GET /me` | The logged-in user's name and role. Roles are `sales`, `hr`, `manager`, `admin`. |
| `POST /ask` | Needs `Authorization: Bearer <token>`. Response now also has `charts` (a list of chart specs) and `moderation` (`{ "status": "ok" | "redacted" | "refused", "notice": text or null }`). |
| New statuses | 401 not logged in or token expired. 404 conversation not found (also used when it belongs to someone else). 429 too many requests (a `Retry-After` header is **assumed**). The earlier 422, 502 and 503 still apply. |
| Refusals | A refused question is a normal 200 answer, not an error. |
| Chart spec | Fields: `id`, `type`, `title`, `subtitle`, `unit`, `series`, `highlight`, `annotations`, `source` (`analysis`, `result_id`, `as_of`), `alt_text`. Only the waterfall shape is defined (`series` items with `label`, `value`, `kind` of `total` or `delta`). Other types are **assumed**. |
| Money in charts | Values arrive in integer cents, and the spec says so with `unit: "money_cents"`. |
| Reports | The answer includes a file path. Downloading needs a backend endpoint that checks who is asking. This is **assumed** and needs my approval (Step U10). |
| `GET /audit` | Optional, `admin` only. Shape is **assumed**. |

If the backend pieces are not built yet, write fixtures from this table, mark each one `"assumed": true`, build against them with the mock client, and replace them with real responses when the backend is ready.

## 3. UI changes

### 3.1 Login and session
- The app opens on a login screen with username and password. Once logged in it shows the chat.
- On load, if a token is stored, call `GET /me`. If it fails, clear the token and show the login screen.
- Wrong credentials show one generic message ("Incorrect username or password"). Never say which part was wrong.
- A 429 on login shows "Too many attempts. Try again shortly."
- An optional "Demo accounts" panel lists the demo usernames. It is switched on by an environment variable and is off by default. Ask me before showing any passwords.
- The header shows the user's name, a **role badge** and a **Log out** button next to "New conversation".
- Logging out clears the token and everything stored for that user, then returns to the login screen.

### 3.2 Role-aware start screen
The empty chat state shows starter questions for the user's role. They are suggestions only. The server decides what is allowed.

| Role | Starter questions (starting set) |
|---|---|
| `sales` | Revenue for November 2024? Top customers in 2024? Was December's revenue drop unusual? |
| `hr` | Headcount by department? What does the leave policy say? |
| `manager` | Give me a sales decline risk report for December 2024. Headcount by department? What changed in December revenue, and what did management report? |
| `admin` | Opens on the audit view (if it exists), otherwise a note that this account has no business data. |

### 3.3 Assistant message layout (top to bottom)
1. Answer text (safe markdown, unchanged).
2. Moderation notice, if any.
3. Charts, up to three, in the order the backend sent them.
4. Report notice, if the answer created a report.
5. Evidence panel: caveats first and visible, then source chips, then figures collapsed (unchanged).

### 3.4 Moderation display
- `redacted`: show the server's `notice` text in a quiet notice under the answer. If `notice` is empty, show "Some content was withheld because of your access level."
- `refused`: the answer is shown as a calm, neutral message, not as an error. There is no Retry button, because asking again will not change the result.
- Never show reason codes, rule names, or any guess at what was removed.

### 3.5 Charts
Each chart is a `ChartCard`:
- **Title** (it states the finding) and **subtitle** (period, filters, unit), straight from the spec.
- The chart itself, with labelled axes, exact values on hover or focus, and the highlighted item emphasised while everything else is muted. Colour is never the only signal, so a highlighted bar also gets a label.
- A **source line**: "From `decline_risk`, as of 15 Jan 2025", built from `source`.
- A **View data** toggle that shows a table of the exact numbers. For money, it shows the formatted value and the exact cents.
- Alt text from `alt_text` (role `img` with an accessible label).
- An optional **Download PNG** (late step, see U12).

Chart types to support, one at a time:

| Type | Used for |
|---|---|
| Ranking bars | Horizontal, sorted, top N plus "Other", highlight one |
| Line | Revenue over time, latest period highlighted |
| Compare bars | Two periods with the change labelled |
| Waterfall | What drove a change: start total, steps, end total |
| Line with expected range | Unusual months: a shaded band and flagged points |
| Side-by-side pair | Orders and average order value, two small charts that stack on a phone |

Heatmaps and stacked bars come later. Any chart `type` the frontend does not know shows its **View data** table and a short note, and nothing is drawn. Never guess a type.

### 3.6 Errors (additions to the existing ones)
- **401 during a session:** go to the login screen with "Your session has expired. Please log in again." Keep the unsent question and offer to resend it after login.
- **404 on a conversation:** quietly start a new conversation and show "That conversation is no longer available, so a new one was started." It must not say whether the conversation existed.
- **429:** show "You're sending requests too quickly." Use `Retry-After` if present, disable sending for that time, then re-enable it.

### 3.7 Reports
The report notice (file name and copy button) stays. Reports are now sensitive, so a download must carry the token. A plain link cannot, so download with a request that sends the token, turn the response into a file, and save that (Step U10).

### 3.8 Admin audit view (optional)
If `GET /audit` exists, `admin` sees an **Audit log** screen: a table of time, user, role, event, decision and reason code, with filters for event type and decision and paging as the backend allows. It never shows question text or restricted values. This is a convenience view. The server decides who may read it.

## 4. Rules

1. **The UI never decides access.** Hiding a button or a starter question is convenience only. Do not write role-to-permission logic in the frontend beyond the starter questions and the navigation.
2. **The token lives only in `sessionStorage`** and is sent only in the `Authorization` header. Never put it in a URL, a console log, stored messages or an error message. Clear it on logout and on any 401.
3. **Storage is per user.** Key stored messages and conversation IDs by user ID. On logout, or if the logged-in user changes, clear the previous user's data before showing anything.
4. **Wrap every storage call in try/catch** and keep working in memory if it fails.
5. **Never show moderation internals.** No reason codes, rule names or hints about what was withheld.
6. **Charts draw only what the spec says.** Geometry arithmetic is allowed (for example, running totals to position waterfall bars). Labels and values come from the spec. If a waterfall's steps do not add up to its end total, do not "fix" it: show the **View data** table, a short note, and log the mismatch to the console in development.
7. **One money helper.** Cents are converted to dollars in exactly one documented function, used only when `unit` is `money_cents`. Do not convert anywhere else.
8. **Display, do not compute** business figures (rule from the first spec, still applies).
9. **Answers are untrusted text.** Safe markdown only, no raw HTML (unchanged).
10. **Errors do not leak.** No raw response bodies or stack traces. A missing conversation and a forbidden one look the same.
11. **Do not change the backend** except in Step U10, which needs my approval first.

## 5. Files

New or changed, inside `frontend/src/` (everything else stays):

    auth/
      authStore.js          sessionStorage token and user, try/catch
      AuthProvider.jsx      React context for the current user (auth only)
      useAuth.js
      LoginView.jsx
    api/
      client.js             CHANGED: adds the token, central 401 handling, 429 and Retry-After
      authApi.js            login() and getMe()
      reportsApi.js         authenticated download (Step U10)
      auditApi.js           optional
      mockClient.js         CHANGED: login and per-role fixtures
    storage/
      conversationStore.js  CHANGED: keys include the user ID
    charts/
      chartRegistry.js      chart type -> renderer, fallback for unknown types
      chartFormat.js        the single money helper and number formatting
    components/
      UserMenu.jsx          name, role badge, log out
      RoleBadge.jsx
      ModerationNotice.jsx
      SessionNotice.jsx
      ChartGrid.jsx         lays out up to three charts, responsive
      ChartCard.jsx
      ChartTable.jsx        the View data table
      charts/
        RankingBarsView.jsx
        LineView.jsx
        CompareBarsView.jsx
        WaterfallView.jsx
        BandLineView.jsx
      AuditView.jsx         optional
    config.js               CHANGED: starter questions per role, demo accounts flag
    styles/
      chartTokens.css       chart colours for light and dark

Also add `mock/fixtures/<role>/` folders for the saved responses.

## 6. Build steps

Each step has a check. Do not start the next until I confirm.

**Step U0: Look before building**
Read the current frontend and the backend's `/openapi.json`. With the backend running (or using assumed fixtures if it is not built yet), log in as each role and save real responses under `mock/fixtures/<role>/`: the login response, `/me`, and `/ask` responses for a ranking question, a trend question, a period change, a sales decline risk report, a refused question, a redacted answer if you can trigger one, plus 401, 404 and 429 responses. Show me the real shape of the token and its expiry, `moderation`, every chart type that came back, and anything structured for severity or the explanation status.
Check: fixtures exist and I have seen the real shapes. If the backend sends a structured severity or "consult a data analyst" field, tell me and we will decide whether to show it.

**Step U1: Auth foundation**
`authStore.js`, `authApi.js`, `AuthProvider.jsx`, `useAuth.js`, and the changes to `client.js` (attach the token, handle 401 centrally, handle 429).
Check: a request without a token is rejected, a valid login stores the token, `GET /me` returns the user, and an expired or bad token clears the session.

**Step U2: Login screen and header**
`LoginView.jsx`, `UserMenu.jsx`, `RoleBadge.jsx`, logout, and the optional demo accounts panel.
Check: wrong credentials show the generic message, a good login reaches the chat, the header shows the name and role, and logout returns to login.

**Step U3: Per-user storage**
Change `conversationStore.js` to key by user ID and clear on logout or user change.
Check: log in as user A, chat, log out, log in as user B. B sees no trace of A, and A's chat is gone after logout. A page refresh keeps the current user's chat.

**Step U4: Role-aware start screen**
Starter questions per role in `config.js`, shown in the empty state.
Check: each role sees its own starter questions, and clicking one sends it.

**Step U5: Moderation display**
`ModerationNotice.jsx`, neutral styling for refused answers, no Retry on refusals.
Check: the redacted and refused fixtures look right, and no reason codes or rule names appear anywhere.

**Step U6: Error additions**
`SessionNotice.jsx` and handling for 401 (with the unsent question kept), 404 (new conversation) and 429 (disabled for the retry time).
Check: each case behaves as in Section 3.6, using the mock client to trigger them.

**Step U7: Chart foundation**
Install the chart library after checking its docs. Build `ChartCard.jsx`, `ChartTable.jsx`, `ChartGrid.jsx`, `chartRegistry.js` and `chartFormat.js`, with the unknown-type fallback. No chart types yet.
Check: any chart fixture shows its title, subtitle, source line and a working View data table, and an unknown type shows the table and a note.

**Step U8: Chart types, one at a time**
Stop and show me after each one.
- **U8a** Ranking bars. Check: sorted, "Other" shown, one item highlighted, values match the spec.
- **U8b** Line. Check: periods in order, latest highlighted, hover values match.
- **U8c** Compare bars. Check: both bars and the change label match the spec.
- **U8d** Waterfall. Check: bars start where the previous one ended, and a spec whose steps do not add up shows the table and a note instead.
- **U8e** Line with expected range. Check: the band, the flagged point and the annotation come from the spec only.
- **U8f** Side-by-side pair. Check: two charts side by side on desktop and stacked at phone width.

**Step U9: Message layout**
Put charts, notices and the evidence panel in the order from Section 3.3.
Check: a risk report fixture shows the answer, up to three charts, the report notice and the evidence panel in order, with no horizontal page scroll on a phone.

**Step U10: Report downloads (ask me first, this changes the backend)**
First, propose to me, without building it, the backend side: an endpoint that serves only the logged-in user's own reports (or reports their role may read), checks the file name, and returns 404 otherwise. Then build `reportsApi.js` so the file is fetched with the token and saved through the browser, and wire the report notice to it.
Check: the download works for the owner, and a different user gets a not-found message. Do not touch the backend until I approve.

**Step U11: Admin audit view (optional, only if `GET /audit` exists)**
`AuditView.jsx` and `auditApi.js`, shown only to `admin`.
Check: the table filters and pages, and no question text or restricted values appear.

**Step U12: Polish**
Keyboard access and focus order inside charts, accessible chart labels, light and dark chart colours, reduced-motion support (no chart animation), phone layout, and an optional Download PNG on `ChartCard`.
Check: every chart works with the keyboard and screen reader labels, and colour is not the only way to see the highlight.

**Step U13: README**
Update `frontend/README.md`: how to log in as each demo role, how mock mode works with per-role fixtures, and how to run backend and frontend together.
Check: a new person can run both and log in as each role from the README.

## 7. Out of scope

Single sign-on, password reset, creating or editing users, remembering the user across browser sessions, charts beyond those listed, heatmaps and stacked bars, editing the policy from the UI, exporting conversations, automated frontend tests, and deployment.

## 8. Done when

I can log in as each role and see only that role's start screen and header. A refused question reads as a calm refusal, and a redacted answer shows a generic notice. Ranking, trend, period-change, waterfall and risk charts render correctly from the specs, each with its source line and a data table. A decline risk report shows its answer, charts and report notice together. Switching users leaves no trace of the previous user. An expired session, a missing conversation and a rate limit each have a clear, safe message. Report downloads (if approved) work only for the right person.
