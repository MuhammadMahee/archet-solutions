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

The manager can help with planning, writing, explanations and code drafting as
well as saved sales reporting. It receives the requester's display name, this
group's title and member display names (including AI teammates), and up to 24
preceding messages from this group. History is capped at 9,000 content characters,
with at most 2,500 per message; older or longer context may need restating.
It cannot execute code, change employee accounts, inspect arbitrary files, send
external messages or act on unconnected business systems. It can read attached
screenshots and capture an explicitly supplied public website as described below.

### Specialist bots and mentions

Ask `@manager Add HR and Finance bots to this group.` The group creator or a
group-member administrator can add HR, Finance, Engineering, Marketing,
Recruiting and Support bots. These are approved role profiles, not new accounts
or independent external services. Additions persist in that group, are audited,
and never grant access to additional business systems. The **AI employees**
directory can insert an add-bot request into the composer for you to send.

Type `@` (or use the @ button) to pick a person or joined bot. Use arrow keys and
Enter/Tab, or tap an option. `@hr` and `@finance` address the corresponding bots;
up to two specialists can reply to one message. Human-only mentions create an
in-app ping without running AI. Bot mentions invoke their replies even when
automatic Manager replies are unchecked. Messages without mentions follow that
checkbox. Human pings get a conversation-list @ badge and a highlighted message;
there are no email, push or operating-system notifications. Mentioned people
must already belong to this group. Use the picker for exact handles.
An explicit `@manager` takes priority over specialist mentions so the Manager
can coordinate the request or add bots.

Migration `013_workforce_agents_mentions.sql` adds private tables for group bot
membership and message mentions. Existing chats keep Manager and Operations.

### Chat, group and message controls

Use a conversation's arrow or right-click it for archive, mute, pin, read/unread,
favorites and custom lists. The header menu adds search, selection, starred and
pinned messages, themes, export, clear and exit. Personal settings persist per
employee; **Clear chat** hides existing history only for that employee.
Mute suppresses the app's unread/mention badges for the selected duration; it
does not configure browser push notifications or operating-system alerts.

Click the group heading for group info, member search, descriptions, photos,
media/reports, links, member tags and member changes. The creator and portal
administrators who belong to the group can edit its profile, add/remove existing
employees, create a similar group and generate/revoke invitations. Invitations
expire after seven days and require an active signed-in portal account. Joining
grants access to existing group history. A departing creator transfers group
ownership to a remaining member, and departing/removed requesters' active tasks
are cancelled. Private replies reuse a conversation between two existing peers
who already share a group; automatic AI replies are unchecked when opening it.

Each message has a menu (also available on right-click): reply, copy, reactions,
forward, pin, star, download, read info, private reply, report and delete. Stars
and **Delete for me** are personal. Authors or group managers can delete a
message for everyone; only managers can pin group messages. Forwarding requires
membership in both groups and copies attachments/saved reports into the target
group's permissions without invoking AI. Reactions and read positions persist.

Disappearing messages can be off, 24 hours, 7 days or 90 days. The setting applies
to new messages; expired content is excluded from history, AI context, downloads
and exports. It is logical expiry, not guaranteed physical database erasure;
downloaded or forwarded copies may remain. Export downloads up to 5,000 visible
messages as JSON with authenticated media references. Search and media/star/pin
collections return up to 200 matches. Reports are saved for portal administrators
under **Group info → Reported items**; no external notification is sent.

Migration `015_workforce_chat_controls.sql` creates private controls tables.
Voice/video calling is not connected.

### Screenshots and image replies

Use **Attach**, paste a screenshot into the composer, or drop an image onto it.
Up to two PNG, JPEG or WebP images can accompany a message. The browser resizes
images (source files up to 10 MB and 20 megapixels); the server validates and
re-encodes them, strips metadata and stores at most 1 MB per image. Click a chat
image to open or download it. Only current group members can fetch its bytes.
Migration `014_workforce_images.sql` stores images in the private chat schema;
the app limits total stored image bytes to 100 MB (base64/database overhead is
additional). This uses the existing database without another storage account.

In Groq mode, bots read attached images using `qwen/qwen3.8-27b` and the existing
`GROQ_API_KEY`, with an 800-token output cap. Image content goes to Groq for this
step; a bounded description is saved for follow-up questions. Free-plan model
permissions and quotas still apply. Gateway and Ollama modes can share images,
but image reading currently requires Groq.

Ask `@manager Send our checklist as a summary image.` Bots render summary cards
locally. These are generated cards, not screenshots of an external application.

Sales reports use the exact **Sales Update → Copy Snapshot** canvas renderer in
`assets/sales-snapshot.js`, shared by the dashboard and chat. The table includes
every saved store row, all metrics, totals, dealer colors and APO/QPay color
scales, omitting the Dealer column just like the dashboard button. Chat renders
the image from the authorized saved report; it does not send private report
data to the public website screenshot service or require a server browser.
Open the image to **Copy Snapshot** or download its PNG; the full CSV is also
available. Existing saved report messages use this layout too.

Ask `@manager Send that using Copy Snapshot.` The `sales_snapshot` action
reattaches the latest completed report in this group, preserving its dates,
filters and figures without a fresh sales query. To change the selection or
refresh the data, request a new sales report instead. Report data and images
remain restricted to current group members.

Ask `@manager Send a screenshot of https://example.com`. Public website captures
use [Microlink's free API](https://microlink.io/pricing), which currently allows
25 requests per day without a key. Shared-service limits apply and captures may
be cached. Only the exact public HTTPS URL in the current request is sent to
Microlink; uploaded images, conversation text, cookies and credentials are not.
URLs with query parameters, login credentials or private network addresses are
rejected. This cannot capture your signed-in portal or interact with a website.
There is no paid fallback or additional environment variable to configure.

Prompts, this bounded chat context and selected sales summaries are sent to Groq. Groq documents that it does
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
2. Open Connection & models. It should show your chosen provider as configured.
   This checks configuration; the first assignment verifies the credentials.
3. Create a chat and request yesterday's saved sales.
4. Confirm the task completes, download its CSV, and compare with Sales Update.

Assignments run during the authenticated send/retry request. Each attempt makes
at most three text model calls, one optional vision call and one read-only sales query;
model calls have a
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

## Persistent AI memory

Migration 016 stores memory in private Supabase tables independently of chat history.
No additional service, paid plan or environment variable is needed.

Manager can extract up to three short durable notes in its existing planning call,
using verbatim evidence from the current request. It does not import old chats or
save entire transcripts, attachments or disappearing messages. Specialists can read
eligible notes; Manager handles automatic saving. Explicit requests such as
"Remember that I prefer concise Dallas updates" receive a server-confirmed result.
Automatic memory defaults on and can be switched off under **Memory**.

Personal notes belong to their author. They are recalled only in chats whose human
members are all within the note's original audience, including new private AI chats.
Manual personal notes default to the author alone. An administrator can explicitly
publish a note as **Company**, making it available to all employees. Other admins
cannot inspect another employee's personal notes. The Memory panel supports review,
search, editing and forgetting notes, with server-side authorization.

Clearing or leaving a chat does not erase its saved notes. Forgetting removes the
note from future retrieval, without rewriting existing messages. In-flight automatic
saves honor opt-out/edit/forget revisions; replies recheck memory availability and
audience permissions. Recall includes at most 30 relevant/recent notes and 6,000
characters, so it is useful background rather than unlimited or perfect recollection.
Current user corrections take precedence over remembered facts.

Verification:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_workforce_memory.py -q
.\.venv\Scripts\python.exe tests/browser_workforce_memory.py
```
