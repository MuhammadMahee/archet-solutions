# AI Workforce on Vercel

This setup uses your existing Vercel project and Supabase database. No Ollama,
PC, tunnel, separate AI server, or always-running worker is required.

## Free-plan option: connect Groq directly

Create a [Groq account and API key](https://console.groq.com/keys) and keep the
account on the **Free** plan. Add these in your Vercel project's Production
environment variables, then redeploy:

```dotenv
WORKFORCE_AI_PROVIDER=groq
GROQ_API_KEY=your_groq_key
```

The app chooses `openai/gpt-oss-120b` on Groq by default; `GROQ_MODEL` and `GROQ_MODELS`
can override the default/allowlist if needed. Existing `WORKFORCE_MODEL` and
`AI_GATEWAY_API_KEY` values are ignored in Groq mode. Model preferences are kept
separately per provider, so an old Gateway model selection does not break Groq.

Groq [retired the former Llama default](https://console.groq.com/docs/deprecations)
for Free/Developer accounts on August 16, 2026. The app translates the old
`llama-3.3-70b-versatile` value to `openai/gpt-oss-120b`, including saved settings,
environment overrides and retried assignments. Requests still go directly to
Groq using the same key. GPT-OSS plans use strict JSON schema output with low
reasoning effort and a 1,200-token completion limit.

Your portal stays on Vercel, chats stay in Supabase, and model requests go directly
to Groq. No Vercel AI Gateway billing verification is used. Send a **new message**
after switching: old assignments retain their previous model and may not be
compatible with the new provider. Existing history and dismiss buttons remain.

Free-plan rate/token limits apply. A quota error stops the assignment; the app
does not upgrade the account, purchase credits, or fall back to a paid provider.
If you independently upgrade the Groq account, that account's usage charges apply.
Vercel and Supabase hosting limits still apply separately.

Prompts and selected sales summaries are sent to Groq. Groq documents that it does
not retain inference content by default, with exceptions for reliability/abuse
monitoring; all customers can enable Zero Data Retention in Data Controls.
Review [Groq data handling](https://console.groq.com/docs/your-data),
[Free-plan limits](https://console.groq.com/docs/rate-limits), and
[billing plans](https://console.groq.com/docs/billing-faqs).

## Alternative: Vercel AI Gateway settings

Keep the portal's existing Supabase and login settings. Add or confirm:

| Environment variable | Value |
| --- | --- |
| `WORKFORCE_ENABLED` | `true` |
| `WORKFORCE_AI_PROVIDER` | `vercel` (also the automatic default on Vercel) |
| `WORKFORCE_MODEL` | `google/gemini-2.5-flash-lite` |
| `SUPABASE_DB_URL` | Your existing Supabase session-pooler connection, port 5432 |
| `AI_GATEWAY_API_KEY` | Optional if automatic Vercel OIDC authentication works; otherwise create a key in Vercel's AI Gateway dashboard |

Use Vercel's server-side environment variables, never frontend JavaScript or Git,
for the API key. `OLLAMA_BASE_URL` is unused in this mode. The app uses Vercel AI
Gateway at its fixed HTTPS address; no backend URL or tunnel key is needed.

Enable/use AI Gateway in your Vercel team dashboard. The app first uses
`AI_GATEWAY_API_KEY`, then falls back to `VERCEL_OIDC_TOKEN`, which Vercel provides
on deployments. Locally, hosted-mode testing requires an API key.
For older Vercel projects, enable "Secure Backend Access with OIDC Federation"
in project settings if using automatic authentication instead of an API key.

Only the configured model is selectable by default. To permit other models, add
`WORKFORCE_MODELS` with comma-separated AI Gateway model identifiers and include
`WORKFORCE_MODEL` in that list. Existing assignments keep their original model.

## Deploy

Deploy this checkout through the Git repository connected to your existing
Vercel project, or through the Vercel CLI. The existing `vercel.json` already
selects Flask, sets a 300-second function duration, and runs the migration script.
The new additive migration `012_ai_workforce.sql` creates private chat/job tables
in `archet_workforce`; it does not change existing portal or sales tables.

The build applies pending migrations only for Production. For Preview testing,
use a separate Supabase database and set `MIGRATE_PREVIEW=true`. Do not point a
preview at production just to test a migration. Redeploy after changing variables.

`INTERNAL_HOST` must match the internal portal domain. Existing preview
`.vercel.app` hostnames are accepted automatically. If using a production
`.vercel.app` hostname instead of your custom domain, set `INTERNAL_HOST` to that
exact hostname.

## Verify

1. Open `/ai-workforce` on the internal portal domain and sign in.
2. Open Connection & models. It should show Vercel AI Gateway as configured.
   This checks configuration; the first assignment verifies the credentials.
3. Create a chat and request yesterday's saved sales.
4. Confirm the task completes, download its CSV, and compare with Sales Update.

Assignments run during the authenticated send/retry request. Each attempt makes
at most three model calls and one read-only sales query; model calls have a
45-second socket timeout and the executor checks a 180-second model-call budget.
Progress is committed between steps and the chat polls for it while processing.
The database connection is closed before inference. No background thread is
expected to survive the function response.

If an invocation is terminated, its saved job becomes retryable after its
330-second lease expires and the chat is refreshed. If a request stops between
saving and starting an assignment, use Start on the pending task. Duplicate sends
with the same message ID do not repeat completed or running work. Cancellation
prevents subsequent work/results; an already-sent model request may still incur
usage. This is bounded request execution, not an unlimited background workflow.

## Costs and data

AI Gateway's published free tier includes $5 per month in model credits for
eligible free-tier accounts. Usage beyond available credits needs funding;
purchasing credits moves the account to its paid tier. Vercel function and
Supabase limits also apply. The app does not enable auto top-up or buy credits.
Inspect usage in your Vercel dashboard.

Prompts and the selected sales summary are sent to the hosted model through AI
Gateway. Raw credentials, customer records, and database connections are not
included in the model context. Chat membership, account status, task ownership,
and allowed sales tools are checked server-side. The private schema is not
accessible with Supabase browser roles.

## Troubleshooting

- **AI Gateway authentication failed:** enable AI Gateway and, if needed, create
  `AI_GATEWAY_API_KEY` in its dashboard, add it to Vercel and redeploy.
- **Credits or rate limit reached:** check AI Gateway usage/limits before retrying.
- **Database unavailable:** confirm `SUPABASE_DB_URL` and that migration 012 ran in
  the target database. Use the session-pooler URL already documented in SETUP.md.
- **Assignment interrupted:** retry once its lease has expired. For recurring
  timeouts, shorten the date range/request or choose a faster allowed model.
- **Model not configured:** select a model allowed by `WORKFORCE_MODELS` and send
  a new assignment.

Local development can still use the existing Ollama/SQLite setup with
`WORKFORCE_AI_PROVIDER=ollama` outside Vercel. Local chats are not automatically
copied to Supabase; production starts with its own conversation history.

## Local verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
.\.venv\Scripts\python.exe tests/browser_workforce.py --hosted
.\.venv\Scripts\python.exe tests/browser_workforce.py --groq
.\.venv\Scripts\python.exe tests/postgres_workforce.py
```

The hosted browser check uses sample accounts/sales and a model double, with no
external worker. The SQL check runs PostgreSQL through an isolated browser/WASM
PGlite instance and downloads a pinned public module. Neither check calls a paid
model or connects to production Supabase. Actual Vercel authentication, network
access, and model availability still require the deployment smoke test above.

References: [Vercel Python AI Gateway](https://vercel.com/docs/ai-gateway/sdks-and-apis/python),
[AI Gateway pricing](https://vercel.com/docs/ai-gateway/pricing),
[Flask on Vercel](https://vercel.com/docs/frameworks/backend/flask),
[Gemini Flash Lite](https://vercel.com/ai-gateway/models/gemini-2.5-flash-lite).
