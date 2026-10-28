# Frontend

Configure the repository root `.env` from `.env.example` and install the
frontend dependencies once from this directory with `npm install`.

Open two PowerShell terminals at the repository root:

Backend:

```powershell
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Frontend:

```powershell
npm --prefix frontend run dev
```

Open the Vite URL shown in the frontend terminal (normally
`http://localhost:5173`). The dev server proxies API requests to the backend.
The interface uses a warm-white, black, and orange palette with a subtle grid.
Recent chats are stored locally in the browser, ordered by latest activity, and
limited to the 15 most recent conversations.
