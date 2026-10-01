# Archet internal workspace setup

## Sales Update and parallel RT-POS imports

### Calling Tree store list

Open **Calling Tree** in the sidebar (or `https://internal.archetsolutions.com/#callingtree`). Admins can upload an `.xlsx` workbook up to 2 MB, preview its stores and dealer counts, then click **Use this Calling Tree**. Members can view the directory but cannot upload or replace it. The uploaded workbook replaces the complete store list across all dealers, while sales history stays intact. Store lists and their versions are stored in Supabase; the workbook is parsed as data and formulas are rejected.

Required headers are **Dealer**, **Store ID**, **Market**, and **Store Name**. Carrier, DM, State, Dealer Code, Door Code, SAP ID, Address, and ZIP Code are preserved when supplied. If several worksheets contain store lists, enter the worksheet name. Unknown dealers, duplicate dealer/Store ID pairs, and invalid rows stop the upload before the active list changes. A preview also fails safely if another administrator replaces the active list before you apply it.

Supported dealer aliases include CONNECT → Connect, SPDI-CA → California, SUPREME → SRH, DF Wireless → AMQ, Arm Wireless → ARM, and ARBF Wireless Metro → ARBF. AMQ and ARM are accepted directly; older ARM1 and ARM2 labels map to AMQ and ARM respectively. Matching uses exact normalized Store IDs within the dealer, not fuzzy store names. Calling Tree names and markets are used in reports. Unmatched IDs remain visible with unavailable metrics until RT-POS reports them.

Only active Calling Tree stores appear in Sales Update, its market/store filters, totals, snapshots, and Excel exports. No active Calling Tree means no sales stores are displayed. Listed stores missing from an otherwise completed source report show zero; unavailable imports show dashes or mark partial totals. The PNG snapshot excludes Dealer and uses the selected market (or ALL MARKETS) and dates in its title. Its vector-style layout has a geometric header, rounded table frame, raised cells with soft shadows and beveled edges, and a prominent totals band. Copy Snapshot and its PNG download fallback export at 1920 pixels wide with height fitted to the report, avoiding empty letterbox space. Very tall reports are scaled down to stay within the 15000-pixel canvas height limit. Cells have darker shadows and a glossy finish; numeric values have no shadows. APO and QPay Conv keep the same gradients as the table. Connect uses the blue palette; other dealers retain their own colors. Partial data is labeled in both the header and footer.

The initial `Calling Tree - Sep-26.xlsx` contains 44 stores: Connect 18, California 12, AMQ 4, ARM 1, ARBF 5, SRH 4. The workbook itself stays outside Git; only the application code and schema migration are committed.

The internal workspace uses compact spacing and shorter table rows at normal browser zoom. The top-left menu button hides or restores the sidebar and remembers the desktop preference; on phones the sidebar opens as a drawer. Sales and Calling Tree dealer filters use searchable dropdowns with keyboard navigation (arrow keys, Enter, Escape).

The Sales Update page is the default internal landing page. It has Dealer, Market, Store, and date filters; Today, Yesterday, Month to date, and custom ranges are supported. Each dealer has a fixed color: Connect deep blue, California burgundy, SRH amber, AMQ royal blue, ARM green, ARBF purple. Excel includes Dealer. Copy Snapshot generates a PNG of the filtered table **without the Dealer column**; if the browser blocks image clipboard access, it downloads the PNG instead.

Six isolated account workers download daily XLS reports in parallel. Each account appears as a separate dealer, including AMQ and ARM. Session and export requests retry temporary connection failures, incomplete downloads, and HTTP 408/429/500/502/503/504 up to three attempts with short delays. Each worker shares a 210-second network budget across its dates so retries fit within Vercel's request limit; unattempted dates remain queued. Invalid credentials, denied access, certificate failures, and invalid report data are not retried blindly. Server logs record safe error codes without cookies or response contents. Store IDs are counted independently within each dealer; a fresh copy wins over a retained copy for the same dealer, store and date. Totals recalculate APO and QPay conversion from summed amounts, rather than averaging store percentages. RT-POS may omit stores from exports; previously saved same-date rows are retained and marked. The importer retains source data independently; the active Calling Tree determines which stores appear in the portal. Migration 004 separates the original ARM accounts; migration 005 renames ARM1 to AMQ and ARM2 to ARM in every Calling Tree version. Store lists, source keys and sales history are preserved.

**Do not share `FW_SessionID` between workers.** Three supplied accounts shared a server session and returned the wrong dealer's stores during verification. The importer deliberately ignores this cookie, uses each account's remembered-login cookies, and obtains a fresh session in a separate cookie jar before exporting. HTTP redirects are restricted to HTTPS RT-POS hosts.

Production variables:

- `RTPOS_COOKIES`: JSON object keyed by `connect`, `california`, `srh`, `arm1`, `arm2`, `arbf`. Each value contains `sec85952EAF_id` and `sec85952EAF_pd`. Keep it in ignored `.env` locally and in Vercel Production secrets. `api/creds.py` remains ignored and is not deployed.
- `CRON_SECRET`: a random secret, identical in Vercel Production and the GitHub repository's Actions secret `CRON_SECRET`.
- Existing `SUPABASE_DB_URL` is used by the importer and reports as well as migrations. Use the session pooler on port 5432.

Vercel functions have bounded lifetimes; there is no infinite background loop. `.github/workflows/sales-refresh.yml` triggers the authenticated Vercel endpoint every hour at :01, :21, and :41. GitHub only sends the trigger; credentials, RT-POS downloads, parsing, and database writes stay on Vercel. GitHub schedules can be delayed and are not a precise timing guarantee. Public repositories may have scheduled workflows disabled after 60 days without activity; monitor the Actions page. See [GitHub scheduled workflow behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule) and [Vercel function duration limits](https://vercel.com/docs/functions/limitations).

For initial setup, deploy successfully (migration `002_sales_performance.sql` runs automatically), then run **Actions → Refresh sales on Vercel → Run workflow**. The first run fills daily dates from the first of the current Central-time month through today. Every Vercel request processes at most four dates per account; the workflow calls again until the backlog is complete. Supabase records progress, so interrupted runs resume. Today is refreshed on schedule and yesterday is finalized after midnight. Errors preserve saved data and retry after 20 minutes. A database advisory lock prevents overlapping refreshes. Only authenticated admins can use **Sync sources**; it forces a new download of today's reports for all six accounts and immediately retries pending or failed imports through today, bypassing the freshness check and retry delays. Both Sales and Quota keep requesting batches while eligible imports remain and downloads make progress. Continuation requests do not force already completed reports to download again. Keep the page open until sync finishes. Source failures preserve saved data and show a retry message; another click retries immediately. If a sync is already running, the button reports that instead of starting overlapping downloads. Reload only reads saved data. Members can read/export. The scheduler endpoint requires its bearer secret and rejects preview deployments.

To renew expired RT-POS access, replace only the affected account's remembered-login cookies in `RTPOS_COOKIES` and redeploy. Import errors are shown on the Sales Update page. No cookie or raw upstream error is returned to the browser or written to logs.

Verification: `python -m pytest -q`, `python tests/browser_sales.py`, `python tests/browser_calling_tree.py`, and `python tests/browser_smoke.py`. Browser checks use synthetic data and save artifacts in ignored `test-results/`. Never commit downloaded sales reports or credentials.

The application is implemented locally. A Supabase project, production environment variables, deployment, and the DNS record still need to be configured. No cloud resources have been created by this code change.

## 1. Create the Supabase project

1. Open [Supabase](https://supabase.com/dashboard), choose **New project**, and choose your organization, project name, region, and database password. Select the plan you want.
2. You no longer need to paste SQL into the SQL Editor. The Vercel production build automatically runs pending files from `supabase/migrations/`. Copy the **Session pooler** connection URI from Supabase's **Connect** dialog (port `5432`) and replace its password placeholder with your database password. Save it as `SUPABASE_DB_URL` in Vercel's **Production** environment variables. This is a PostgreSQL URI, not the HTTPS project URL or API secret key. URL-encode special characters in the password. [Supabase connection instructions](https://supabase.com/docs/guides/database/connecting-to-postgres).
3. Under **Authentication → Sign In / Providers**, disable **Allow new users to sign up**. Leave email/password sign-in enabled. All accounts are created through the admin panel, not public registration.
4. Set the Auth Site URL to `https://internal.archetsolutions.com` under **Authentication → URL Configuration**.
5. Copy the project URL and server **secret key** into the existing local `.env` as `SUPABASE_URL` and `SUPABASE_SECRET_KEY`. For a legacy service-role JWT, use `SUPABASE_SERVICE_ROLE_KEY` instead. Never use a publishable/anon key here; never put the secret key in HTML.

Passwords are managed by Supabase Auth. Usernames map to internal Auth identifiers such as `mahee@users.internal.archetsolutions.com`; these are not mailboxes, and no email confirmation is sent. Account roles and active status are checked by Flask on every protected request. All application tables have RLS enabled and browser access revoked. See [Supabase API security](https://supabase.com/docs/guides/api/securing-your-api) and [admin account creation](https://supabase.com/docs/reference/python/admin-api).

## 2. Create your permanent owner

From this project directory:

```powershell
python -m pip install -r requirements.txt
python scripts/migrate.py
python scripts/bootstrap_owner.py
```

For these local commands, put `SUPABASE_DB_URL`, `SUPABASE_URL`, and the API secret key into the ignored local `.env` first. If the production build already applied the migration, the local migration command simply skips it.

The ignored local `.env` is already prepared with username **Mahee**'s requested initial password in `ARCHET_OWNER_PASSWORD`. If that variable is absent, the script prompts privately for a password. The script never changes an existing owner's password. After verifying login, remove `ARCHET_OWNER_PASSWORD` from `.env`; do not add it to Vercel. Automatic SQL migrations do not create Auth accounts; this owner bootstrap is still a one-time command.

Mahee is a permanent administrator: the application and database prevent deleting, disabling, renaming, or demoting this account. The owner can change their own password in Settings. Other admins cannot reset the owner's password through the panel. If the owner loses their password, the Supabase project owner can reset it in Authentication and must also revoke the owner's app sessions:

```sql
update public.portal_users
set session_version = gen_random_uuid()
where is_owner = true;
delete from public.portal_sessions
where user_id in (select id from public.portal_users where is_owner = true);
```

For password changes, bans, or deletion performed directly in Supabase rather than through this app, also revoke the affected user's portal sessions and replace their session version. App sessions are separate from Supabase Auth tokens.

## 3. Test locally

```powershell
python api/index.py
```

- Public website: `http://localhost:5000/`
- Internal workspace: `http://localhost:5000/internal`
- Sign in as Mahee, open **Accounts**, and create a team account.
- Members can view all quote requests and save follow-up notes/status. Admins can also create users, reset member/admin passwords, change roles, and disable accounts.
- Submit a test quote on the public site and verify it appears in the inbox.
- **Keep me signed in** uses a persistent cookie for 30 days. Ordinary sessions last up to 12 hours. Accounts are permanent; sessions expire and are revoked on logout, account changes, and password resets.

The existing public frontend is preserved in `public.html`. `index.html` is the new internal portal. `api/index.py` is the backend entry point, using `api/portal.py` and `api/supabase_store.py` as helpers. Local development loads `.env`; production uses Vercel environment variables.

## 4. Deploy to the existing Vercel project

Push this folder to GitHub and connect that repository under **Vercel → Project → Settings → Git**. Set your production branch (usually `main`). Keep the existing `archetsolutions.com` domain attached. Commits to that branch trigger a production build and database migrations automatically.

The committed `vercel.json` selects the Flask framework and runs `python scripts/migrate.py` after dependencies install and before the app is deployed. `pyproject.toml` points Vercel to `api.index:app`. The old `builds`/`routes` configuration has been replaced so the Flask build command runs. Keep the repository root as the Vercel Root Directory and leave Install Command and Output Directory at their defaults. [Vercel Flask build commands](https://vercel.com/docs/frameworks/backend/flask#build-command).

Add these values in **Vercel → Project → Settings → Environment Variables** for Production, then redeploy:

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_SECRET_KEY` | Server secret key (or use `SUPABASE_SERVICE_ROLE_KEY` for a legacy key) |
| `SUPABASE_DB_URL` | Supabase **Session pooler** PostgreSQL URI, port `5432`, including database password |
| `INTERNAL_HOST` | `internal.archetsolutions.com` |
| `SITE_URL` | `https://archetsolutions.com` |
| `EMAIL_FROM` | Gmail address used to send notifications |
| `EMAIL_TO` | Inbox that receives quote notifications |
| `EMAIL_APP_PWD` | A replacement Gmail app password |

The old code contained a Gmail app password. It has been removed from source; revoke it in the Google account and use a replacement in environment variables. Quotes now save to Supabase before email is attempted, so an email outage does not lose a submission. The inbox records the notification delivery status; it does not automatically retry failed mail. Existing historical submissions are not imported automatically because no lead backup file was present in this workspace.

Production builds fail if the database URL is missing or a migration fails. Preview builds skip migrations by default. To migrate a separate preview Supabase project, add that project's values to the Preview environment and set `MIGRATE_PREVIEW=true` there. Keep production credentials scoped to Production. Visit the preview deployment's `/internal` path to test the UI.

### How automatic migrations work

- Completed migrations are recorded with checksums in `archet_private.schema_migrations`. Redeploying skips them.
- New files run in numeric order. For the next database change, add `002_descriptive_name.sql`, then `003_...sql`, and push. Do not edit or remove an already-applied file.
- The runner owns the transaction; do not add `BEGIN`, `COMMIT`, or `ROLLBACK` to migration files. All pending SQL and its history records commit together. On failure, this run rolls back and deployment stops.
- A database transaction lock serializes simultaneous builds so they cannot apply the same migration twice. A lock wait longer than 60 seconds fails the build; retry it after the other build finishes.
- Migrations do not run when someone opens the website or logs in. They run during builds. Keep future schema changes compatible with the currently running app: database changes commit before Vercel promotes the deployment, and an app rollback does not undo database migrations.
- A GitHub push triggers this only when the repo is connected to Vercel. No separate GitHub Actions workflow or GitHub database secrets are needed.

### If you already ran the original SQL manually

If `001_internal_portal.sql` already completed successfully in the SQL Editor, the first automated run will report existing tables. After verifying that the entire original migration was applied, record it once from your local terminal:

```powershell
python scripts/migrate.py --baseline 001_internal_portal.sql
```

This records migration history without executing SQL or deleting existing data. Do not use it for an empty or partially configured database. Then redeploy; future migrations will run normally.

## 5. Connect internal.archetsolutions.com

1. In the **same Vercel project**, open **Settings → Domains → Add Domain**.
2. Enter `internal.archetsolutions.com`. Attach it to the Production environment; do not configure it as a redirect to the public domain.
3. Vercel displays the DNS record required for this project. At the service managing your domain's DNS, add that record. For a subdomain, it is normally a **CNAME** with **Name/Host `internal`**. Copy the exact target shown by Vercel; do not guess the target.
4. Keep the existing apex (`@`) and `www` records intact. If there is already a record for `internal`, resolve that record's conflict only.
5. Wait for Vercel to report **Valid Configuration** and issue the HTTPS certificate, then open `https://internal.archetsolutions.com`.

No separate domain purchase or wildcard DNS record is needed. Flask chooses the portal for the internal hostname and the existing marketing site for the public hostname. Vercel routes both hosts through the backend; secure login cookies are restricted to the internal host. See [Vercel's domain setup instructions](https://vercel.com/docs/domains/working-with-domains/add-a-domain).

## Verification

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

For the optional real-browser checks:

```powershell
python -m playwright install chromium
python tests/browser_smoke.py
python tests/browser_quota.py
python tests/browser_invoices.py
```

The browser check exercises the real frontend and Flask backend against fake Supabase data, including desktop/mobile layout, account creation, follow-ups, disabling accounts, password changes, and logout. Screenshots are saved under the ignored `test-results/` directory.

The automated tests use a fake Supabase service to check authentication, account authorization, session revocation, CSRF protection, validation, and durable quote handling. They do not prove the hosted migration or DNS configuration. After deployment, verify both hostnames, owner login, member permissions, logout, disable/reset behavior, and persistence of a public quote submission.

## Invoices

Only the permanent **Mahee** owner can open **Invoices** or read/write its API. Other administrators and members cannot access invoice data. Migration `008_invoices.sql` creates the private ledger table; `009_named_invoices.sql` adds invoice IDs, names, and a private search function. Migration `010_invoice_payment_summary.sql` combines existing market advances into the invoice-level advance and adds the invoice remark. Existing invoices remain available with their amounts preserved. Migrations run through the existing production build command; for local development, apply pending migrations with `python scripts/migrate.py` against the intended database.

Enter an **Invoice name**, choose a month, add each dealer/market, and enter the store count, full-month rate per store, days worked, and optional market remark. Calling Tree names are suggested, and manual names are also supported. **Potential Pay = stores × monthly rate × days worked ÷ calendar days in the invoice month**. The denominator automatically handles 28, 29, 30, and 31 days. Days worked accepts whole numbers from zero to the month's length; new and historical rows default to a full month. Changing months adjusts full-month rows to the new month's length; partial-day entries retain their entered count and must still be valid for the new month. Potential pay is rounded once per market to the nearest cent, with half cents rounded up.

Below the market ledger, enter **Advance Already Paid** once and an optional **Invoice remark**. **Total Payable = sum of Potential Pay − Advance Already Paid**; negative totals represent credit. Amounts are in USD. Click **Save changes** to write the complete invoice, including days, advance, and both kinds of remarks, to Supabase; later saves update the same invoice. **New invoice** starts an independent invoice, including another for the same month. A stale tab cannot overwrite a newer save. Historical entries without a store count default to one store, and entries without days worked default to the full invoice month, preserving their existing totals.

Expand **Saved invoices** to search invoice names (case-insensitive), filter by month, or browse pages of 20 results ordered by last save. **Open** restores the name, month, and all market entries for viewing, editing, or printing. The URL retains the opened invoice ID so a reload reopens it after authentication. Names can be changed without creating a duplicate. Invoice names and references also appear on the A4 printout. Leaving a modified invoice for another invoice prompts before discarding changes.

**Print / PDF** saves the invoice first, then opens an A4 portrait print layout. Select **Save as PDF** in the browser print dialog; turn off browser headers and footers for a clean document. Longer invoices continue across pages with repeated table headings. The printout includes all markets, remarks, advances, totals, and the invoice period. Browser tests use fake data and save desktop/mobile screenshots and sample PDFs under `test-results/`.

## Account rest mode

On **Accounts**, only the permanent owner **Mahee** can click **Take a Rest** to pause an account and **Back to Work** to restore it. The permanent owner and the acting administrator's own account are protected. Rest differs from disabling: the user can authenticate, but only their session status and sign-out remain available; all protected report, export, account, upload and editing APIs reject access. Existing sessions detect changes every five seconds while visible, and when the tab regains focus. Returning to work restores access without another login.

The rest screen replaces the workspace, clears loaded report data and hides navigation. It shows the configured first-login message, then the eggplant message on the first reload in the same tab. The next three reloads show the three supplied images in attachment order, fitted to the screen without cropping. Further reloads keep the final image. Polling does not advance the sequence; a new rest episode or a fresh sign-in resets it. Migration `007_account_rest.sql` adds the persistent rest state; all accounts start with rest off. Run `python tests/browser_rest.py` to check the admin/user flow with simulated authentication.

## Quota Update

Open **Quota Update** in the sidebar. An administrator can expand **Manage monthly goals**, select a dealer and month, and download a template populated with that dealer's active Calling Tree stores. Enter goals, upload the workbook, review the preview, and click **Apply goals**. This replaces only that dealer's goals for the selected month. Members can view and export reports, but cannot upload goals.

The importer accepts the `spdi-ca` Goals layout (`Market`, `Stores`, `Voice`, `BTS`, `HSI/HINT`, `Acc`, optional `MIM`) and the new template with `Store ID`. Files must be `.xlsx` or `.xlsm`, at most 2 MB, with up to 5,000 rows. Macros are never executed. Formulas require cached results saved by Excel; otherwise replace formulas with values. Duplicate store rows are combined. Legacy files match market and store name within the selected dealer; Store ID is preferred and survives store renames. Unmatched or ambiguous stores are rejected before any data changes. Reports always follow the current Calling Tree, including after a replacement.

Migration `006_quota_update.sql` creates the private monthly goals tables automatically on production deployment. Actuals use the existing saved RT-POS imports, so the scheduled sales sync also updates quota progress without another download worker. Upload goals separately for each dealer; old SPDI portal goal data is not copied automatically.

ARBF does not use accessory goals. Its template omits Acc, uploads accept workbooks without that column, and any legacy Acc values are ignored. ARBF's overall score and rankings use quota growth alone. Its report, snapshots and Excel hide accessory goal, remaining, per-day goal and achievement columns; accessory actuals and trend remain available. With multiple dealers selected, those goal fields show a dash on ARBF rows. Combined accessory target calculations exclude ARBF's goals and sales, while total accessory actuals and trend still include all dealers. Combined overall averages total quota growth with the accessory achievement of dealers that have accessory goals; ARBF-only overall is quota growth.

Calculations follow `spdi-ca`: Voice actual = new activations + reactivations - BTS - HSI; upgrades are excluded. Total quota includes Voice, BTS, HSI and optional MIM goals; MIM actual is zero. Growth is actual / goal. Accessory trend is actual / elapsed days * days in month; per-day goal is remaining accessories / remaining days after today. Projected accessory achievement is trend / accessory goal. Overall average is the average of quota growth and projected accessory achievement. Zero denominators produce zero. Central time determines elapsed days. Past months use all their days, while future months have zero actuals and elapsed days. Rankings restart per dealer and market with competition ties (1, 1, 3). Totals use aggregate goals and actuals, not an average of store percentages.

The page includes Voice, BTS, HSI/HINT and achievement-summary tables, month/dealer/market/store filters, four-sheet Excel export and individual PNG snapshots. Snapshot images are 1920 pixels wide with height fitted to their contents, and omit the Dealer column. Select at most 350 stores per snapshot; Excel includes all filtered stores. Missing sales show a dash; partial or stale actuals, totals and rankings are labeled provisional.
