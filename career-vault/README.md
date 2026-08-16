# Career Vault MVP

Local-first Career Vault for guided career intake, job-fit analysis, and evidence-backed resume generation.

## First run

Keep Ollama running locally, then install project dependencies:

```bash
cd "/Users/krishnaagrawal/Documents/Codex/2026-08-16/hey-gpt-so-today-is-sunday/outputs/career-vault"
bash scripts/setup-project.sh
```

Start the backend in Terminal window 1:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend in Terminal window 2:

```bash
cd frontend
npm run dev
```

Open the URL shown by Vite, normally `http://127.0.0.1:5173`.

## What is included now

- React dashboard for the guided Career Interview foundation
- FastAPI health and local-system endpoints
- SQLite database initialization at `data/career-vault.db`
- Ollama provider that verifies the required local models
- A provider boundary so Ollama can later be replaced by a cloud LLM provider

No user data leaves the Mac. The first application feature to implement next is the guided Career Interview and fact-confirmation flow.
