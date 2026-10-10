# AI Workforce: local development and operation

**Deploying on Vercel? Start with [VERCEL_AI_SETUP.md](VERCEL_AI_SETUP.md).**
The instructions below describe the optional local Ollama development setup.

The first working slice adds **AI Workforce** to the existing portal at
`/ai-workforce` (or `/internal#workforce`). It supports personal AI chats, groups
created by admins using existing employee accounts, saved messages, AI Manager
delegation to Operations, read-only saved sales reports, task progress, cancellation,
retry, activity logs, and CSV downloads. Messages identify their human or AI author.

The manager makes a real, schema-constrained local-model plan. The worker validates
it, invokes the approved sales service, calls Operations with the result, then asks
the manager for a final response. A bounded Python orchestrator allows at most
three model calls and one sales tool call per attempt. There is no agent recursion.

The existing portal uses Flask, plain JavaScript, and Supabase, with Vercel
deployment configuration. The AI packages are separate from production
requirements so installing them locally does not change the deployed portal.

## Python environment

From the repository root in PowerShell:

```powershell
python -m venv .venv
& .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt -r requirements-ai.txt
& .\.venv\Scripts\python.exe -m playwright install chromium
& .\.venv\Scripts\python.exe -m pip check
```

Select `.venv\Scripts\python.exe` as the interpreter in your editor. Activation is
optional; the commands here use the interpreter directly and do not require a
PowerShell execution-policy change.

The optional AI packages provide:

- Ollama's Python client for local inference and embeddings.
- LangGraph and SQLite checkpoint storage for agent orchestration development.
- Flask-Sock for a future persistent WebSocket backend.
- PyPDF and python-docx for PDF and Word parsing.
- pandas, existing openpyxl/xlrd, and matplotlib for spreadsheets and reports.

The current worker uses the Python standard library and its own durable SQLite job
queue. LangGraph, embeddings, document parsers, and Flask-Sock are installed for
later expansion; they are not required by the first slice. No paid model provider
is configured. LangSmith is a transitive development dependency; hosted tracing
is not used.

## Ollama and models

Install the official Windows application:

```powershell
winget install --id Ollama.Ollama --exact --source winget --silent --accept-source-agreements --accept-package-agreements
```

Restart the terminal after installation so it picks up the new PATH. Alternatively:

```powershell
$ollamaExe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
& $ollamaExe --version
& $ollamaExe pull qwen3:1.7b
& $ollamaExe pull nomic-embed-text
& $ollamaExe list
& $ollamaExe run qwen3:1.7b
```

Qwen3 1.7B is a small starting model for this machine's approximately 16 GB RAM
and integrated Intel graphics. Evaluate its accuracy before using it for company
tasks; larger models can be selected later on suitable hardware. Nomic Embed Text
provides local document embeddings. Models are shared between future AI employee
profiles rather than downloaded separately for each employee.

Ollama normally runs in the background. If its API is unavailable, start it in a
terminal with `ollama serve`. Keep its listener on `127.0.0.1:11434`.

```powershell
Invoke-RestMethod http://127.0.0.1:11434/api/version
Invoke-RestMethod http://127.0.0.1:11434/api/tags
```

Optional configuration in your ignored `.env` (defaults are shown):

```dotenv
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen3:1.7b
WORKFORCE_ENABLED=true
# WORKFORCE_DB_PATH=C:/path/to/persistent/workforce.sqlite3
```

## Start the portal and worker

Keep the existing Supabase authentication and sales variables in `.env`. No new
employee accounts or Supabase migrations are created. In two PowerShell terminals,
from the repository root:

```powershell
# Terminal 1: existing portal, including the new module
& .\.venv\Scripts\python.exe -m flask --app api.index run --host 127.0.0.1 --port 5000
```

```powershell
# Terminal 2: persistent queue consumer
& .\.venv\Scripts\python.exe scripts/workforce_worker.py
```

Open `http://127.0.0.1:5000/ai-workforce` and sign in with your existing portal
account. Create a conversation and send “Summarize yesterday's saved sales for all
stores.” An administrator can add other active team members at group creation.
Uncheck **Assign to AI Manager** to send a human-only message to the group.

**Connection & models** shows installed models, worker availability, and configured
integrations. Admins can select an installed local chat model. Embedding-only models
and cloud-backed models cannot be used for assignments. New assignments use the
selected model; an existing task, including its retry, keeps its original model.

The web process never starts workers or runs inference inside a request. Messages
and pending jobs persist if either process stops. A worker heartbeat renews its job
lease. Interrupted running jobs become failed and can be retried when a worker
restarts. Manual retries are limited to three attempts. Cancellation immediately
marks the task cancelled; an already-running model HTTP call can finish in the
background, but its output is discarded and subsequent steps do not execute.

## Storage, permissions and API

The local schema is created automatically in `.data/workforce.sqlite3`, or at the
configured `WORKFORCE_DB_PATH`. The web process and worker must use the same file
on a local, persistent disk. SQLite WAL mode and atomic claims support concurrent
web requests and prevent two workers from claiming the same assignment. Tables:
`conversations`, `members`, `messages` (ordered sequence and unique client request
ID), `tasks` (state and worker lease), `audit`, `settings`, and `workers`.
This is independent of existing Supabase tables. Back up the SQLite database with
the SQLite backup API, or stop both processes before copying its database/WAL files.
Restrict filesystem access to the server account; do not commit `.data/`.

All endpoints sit under `/api/internal/workforce/` and reuse portal cookies, host
checks, CSRF checks, rest mode, account status, and session revocation. Reads and
downloads require conversation membership; being an admin alone is insufficient.
Only the assignment creator can cancel or retry it. Account role, active/rest state,
and session version are checked again before model/tool steps and publication.

The existing Sales Update endpoint gives both active admins and members access to
saved sales. This module applies that same policy; the portal currently has no
department/record-specific user scopes. The tool reads through the existing sales
service and its read-only, parameterized transaction and Calling Tree allowlist.
There is no model-generated SQL or shell execution. If narrower sales access is
introduced later, update the sales service and workforce authorization together.

| Endpoint | Purpose |
| --- | --- |
| `GET status` | Model list, employee directory and connection status |
| `PATCH settings` | Admin selection of the default local model |
| `GET/POST conversations` | List accessible chats / create one with `title`, `member_ids` |
| `GET conversations/{id}?after=N` | Ordered messages after a cursor and recent task states |
| `GET conversations/{id}?before=N` | Earlier message history, 100 at a time |
| `POST conversations/{id}/messages` | `content`, UUID `request_id`, boolean `invoke_agents` |
| `POST tasks/{id}/cancel` or `/retry` | Creator-only task control, JSON `{}` |
| `GET tasks/{id}/report.csv` | Authorized download after successful completion |
| `GET tasks/{id}/audit` | Authorized execution activity |

The UI polls every two seconds while visible, deduplicates by sequence, and resumes
from persisted history after reconnect/reload. It follows the portal's polling
approach; token streaming and WebSockets are not implemented. Unread indicators
are session-local, not read receipts. Search covers loaded messages; load earlier
history to search older content. The UI escapes all model text before rendering
limited bold/code formatting. CSV text cells are protected against formula injection.

Each AI message is treated as an assignment with explicit dates and filters, not
as an unlimited conversation-memory agent. The model sees at most 12 store rows
plus complete totals and coverage; the CSV contains all returned rows. Missing
data, retained records, or incomplete imports must be considered when reviewing
AI summaries. Source totals beneath the final response are rendered directly from
the tool result, independently of AI prose. The CSV contains the complete tool
output and remains downloadable from the saved final message.

## Deployment and current limits

For Vercel deployment, follow [VERCEL_AI_SETUP.md](VERCEL_AI_SETUP.md). Vercel
uses AI Gateway for hosted inference and the existing Supabase PostgreSQL database
for persistent chats. Assignments execute during bounded function requests; no
local Ollama service, tunnel, or worker is required. Migration 012 adds private
Workforce tables. The local setup described above remains available separately.

Finance/HR agents, commissions, targets, file uploads, knowledge retrieval,
membership editing, message edits/deletion/reactions, employee-profile editing,
and external action approvals are not implemented in this first slice. Unsupported
integrations are shown as not connected. No consequential external write tool is
available. Model instructions are not a security boundary: tool selection,
argument validation, membership and user authorization are enforced in Python.

## Troubleshooting

- **Worker offline:** start `scripts/workforce_worker.py` with the same `.env` and
  database path as Flask. Jobs stay pending until a worker is available.
- **Ollama unavailable:** start Ollama, check `/api/version`, then retry. Individual
  generation requests time out after 180 seconds of socket inactivity.
- **Model unavailable/incomplete response:** select an installed local chat model
  and send a new assignment. Try a shorter request on this CPU-only machine.
- **Sales assignment failed:** check the existing Sales Update page and
  `SUPABASE_DB_URL`. Missing database access produces a failed task, not sample data.
- **No matching sales rows:** use the exact market spelling shown in Sales Update.
- **Access changed:** sign in again; revoked, disabled, or resting accounts cannot
  continue work. Retrying uses the requester's current session version.

## Verify the existing portal

```powershell
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe tests/browser_smoke.py
& .\.venv\Scripts\python.exe tests/browser_workforce.py
# Real local-model end-to-end run; accounts and sales remain explicitly synthetic.
& .\.venv\Scripts\python.exe tests/browser_workforce.py --live-ollama
```

These checks use simulated Supabase data and an isolated temporary SQLite database.
The workforce browser shows a **DEMO WORKSPACE** banner. `--live-ollama` exercises
actual local inference, manager delegation, the authorized tool, persisted results,
CSV download and browser rendering. It never calls the production sales database.
Browser screenshots and the sample report go to `test-results/workforce/`.

References: [Ollama Windows setup](https://docs.ollama.com/windows),
[Qwen3 1.7B](https://ollama.com/library/qwen3:1.7b),
[Nomic Embed Text](https://ollama.com/library/nomic-embed-text).
The model integration uses [Ollama chat](https://docs.ollama.com/api/chat) and
[schema-constrained outputs](https://docs.ollama.com/capabilities/structured-outputs).
