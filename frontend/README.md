# Frontend

Configure the repository root `.env` from `.env.example` and install the
frontend dependencies once from this directory with `npm install`.

For MongoDB mode, set `MONGODB_ENABLED=true`, configure `MONGODB_URI` with your
MongoDB Atlas connection string, ensure Atlas Network Access allows your
machine and the database user has access, then ingest the sample documents and
policies from the repository root:

```powershell
.\.venv\Scripts\python.exe -m scripts.ingest_mongodb
```

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
Generated Word reports appear as downloadable document cards in the chat.
