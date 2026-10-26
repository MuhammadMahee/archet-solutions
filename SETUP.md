# Archet internal workspace setup

## AI Workforce

The AI Workforce module is available at `/ai-workforce` or from the workspace
sidebar. See [AI_SETUP.md](AI_SETUP.md) for the separate worker command, Ollama
configuration, storage/access rules, tests, and production hosting requirements.
This first slice supports AI Manager/Operations collaboration over saved sales.
For Vercel deployment, follow [VERCEL_AI_SETUP.md](VERCEL_AI_SETUP.md).

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

## Store Opening / Closing

The sidebar has one **Opening / Closing Spreadsheet** entry at `/spreadsheet`. The former Form and Report pages are retired; their saved links redirect to the spreadsheet. Signed-in members can edit reviews and add missing employees. Administrators can use **Data > Sync RT-POS sources** and **Data > Upload store schedules** directly in the sheet. Schedule uploads show a workbook preview before applying changes, including any Connect opening-time corrections. **File > Copy snapshot** and **File > Download Excel** provide the report outputs. Saved data and version history are preserved. Run `python tests/browser_store_hours_navigation.py` to verify navigation, redirects, and schedule uploads on desktop/mobile.

The table supports spreadsheet navigation and editing on the current page (up to 100 rows). Click a cell and use arrows, Tab, Enter, Home/End, Ctrl+Home/End, or Page Up/Down. Shift+arrows, Shift+drag, or Shift+click extends a rectangle; Ctrl/Command+click or drag adds a separate range. Ctrl/Command+Space selects entire columns; Shift+Space selects entire rows on the current page. Column headings and row numbers select columns and rows. The Range box accepts addresses such as `G1:G10` or `G1:G10, K1:K10`. Up to 50 separate ranges support editing, fill, and clear operations; overlapping cells are changed once. Copy, cut, paste, and flash fill require one continuous range. All 14 data columns are editable in the spreadsheet, including dates, market/store/employee names, RT punches, statuses, and chargeback amounts. Migration `020_store_hours_cell_overrides.sql` stores corrections separately from imported data; syncs preserve them. Date corrections use the corrected date in report filters and resolve workbook hours for that weekday after saving. Store and employee corrections apply to the individual row while retaining its original source identity; they do not rename directory entries or move source punches.

Use **Edit cell**, F2, double-click, or typing to edit a cell. Time columns accept AM/PM or 24-hour times; dates accept YYYY-MM-DD or MM/DD/YYYY ending today or earlier; chargebacks accept signed amounts with up to two decimals; text cells accept up to 160 characters. Ctrl+C/X/V copies, cuts, and pastes tab-separated ranges compatible with Excel and Google Sheets. Paste validates every target and value before changing any cell; one copied value fills a selected range. Ctrl+D fills down from the top selected row; Ctrl+R fills right from the leftmost selected column. On a single cell these copy from above or left. Ctrl+Enter in the editor fills selected cells with the entered value when compatible with their column types. Ctrl+E previews flash fill from two examples in one time column: repeated times or a constant time interval, filling blank cells only after **Apply suggested times**. It does not infer names, arbitrary text transformations, or Excel formulas.

**F8** opens a command menu instead of Excel's Alt ribbon; then press a displayed letter (for example D to fill down, S to save, T for the tutorial). The menu contains the supported report actions, not the full Excel ribbon. Shortcuts are scoped to the focused grid and leave browser shortcuts elsewhere intact. Command can replace Ctrl on Mac. **Tutorial** / F1 opens a five-step walkthrough and shortcut guide, with a dismissible first-use introduction saved per signed-in user/browser. Mobile users can use Edit cell and the command buttons.

The spreadsheet autosaves after edits; **Save changes** / Ctrl+S saves immediately. Ctrl+Z and Ctrl+Y / Ctrl+Shift+Z undo and redo up to 100 operations; undo history resets on reload, filter/page changes, or sign-out. Dedicated spreadsheet autosaves preserve undo history; undo creates a new saved version. Clipboard and fill actions never alter original source punches. Purple corner markers identify corrections. **F8 then U ? Use source/default** removes selected corrections, restores imported values and automatic calculations, and clears camera/schedule overrides. Manual statuses and chargebacks stay fixed until reset. Clearing a date restores its source date; clearing RT punches explicitly marks them missing. Every saved correction and reset is captured in protected version history.

The dedicated **Opening / Closing Spreadsheet** opens at `/spreadsheet`, from its portal navigation entry. It uses the existing portal session and has its own sign-in screen when needed. The page has no sidebar: menus, a formatting toolbar, a cell-value bar, row numbers, column letters, and a full-window grid. The cell-value bar edits plain values; formulas are not evaluated. F8 remains the command menu, and Ctrl/Command+B, I, and U apply bold, italic, and underline to selected cells. Ctrl/Command++ (also Ctrl+= or numpad plus) and Ctrl/Command+- follow the selection. Select whole rows with Shift+Space or row numbers: plus opens Add employee row with the selected store and date filled in; minus removes the selected rows after confirmation. Select a whole column with Ctrl/Command+Space or its heading: plus adds a custom column; minus removes the active custom column. A normal cell selection keeps the column shortcuts. Default columns remain protected. Adding a column selects it immediately. Removed rows stay out of the sheet, reports, snapshots, and Excel exports after reload or source sync. **Edit > Restore removed rows** brings back their saved values and formatting within the current report filters. Removal and restoration create protected history versions; neither deletes prior versions. Migration `022_store_hours_removed_rows.sql` adds this reversible state. Run `python tests/browser_store_hours_structure.py` to verify selection routing, save-before-remove, restoration, history, and protected columns. The green active-cell border glides between cells over 110 ms while focus and edits update immediately; system reduced-motion settings disable this animation. Moving to an offscreen column glides the sheet horizontally over 320-440 ms, easing gently to a stop and leaving up to 32 px of breathing room beyond the selected cell. Longer jumps get more animation time; rapid navigation retargets the current scroll and mouse/touch scrolling cancels it.

Use **+ Column** to add a shared custom column (up to 40 active columns). A heading's dropdown offers sorting, text-contains and value filters, and custom-column rename/delete. Default report columns are protected on both the UI and API. Column changes save immediately for all users, with revision checks against concurrent changes. Deletion archives a custom column; its definition, saved values, formatting, and prior versions remain. Migration `021_store_hours_spreadsheet.sql` adds the shared column settings and per-review `custom_cells` / `cell_formats`, captured by the existing protected audit triggers. The archive retains up to 200 column definitions.

Formatting supports 12 font families (including Calibri, Arial, Aptos, Cambria, Times New Roman, and Consolas), bold, italic, underline, text/fill colors, 8?28 point font sizes, left/center/right alignment, wrapping, and automatic/text/number/currency/percent/date/time presentation. Formatting is saved per cell with the row's review revision, survives source syncs, and supports draft undo/redo. Custom columns have a default number format that can be edited through their rename dialog; individual cell formats take precedence. The Borders control applies all, outer, inner, horizontal, vertical, individual-edge, or no borders to selected cells, with thin, medium, thick, dashed, dotted, or double lines and a custom color. Font and border changes autosave, support undo/redo, and appear in Excel exports. Employee names display in uppercase in the dedicated sheet, clipboard copies, snapshots, and Excel; original source spelling is retained. Clear formatting restores default presentation. Sheet row and column selections affect the current page of up to 100 rows, while filters and sorting cover the complete selected period. The dedicated sheet autosaves 1.2 seconds after editing stops, without reloading data or moving the selection. Period changes, column changes, syncs, and exports wait for pending saves. Failed saves retain drafts and show a retry status; Ctrl+S or Save changes retries immediately. The date button opens a single-day/range calendar, including earlier months; the URL retains the chosen period across reloads. Shift+Space selects rows and Ctrl/Command+Space selects columns. The Archet logo, green active-cell rectangle, range borders, and animated copy/cut outline follow the desktop spreadsheet layout. Cut marks a pending move until a successful paste inside this sheet; Escape cancels it. Copying/cutting to another application does not delete source cells.

**File ? Download Excel** exports every matching saved row, active custom columns, and saved formats. Column filters, sorting, and free-text row search are applied again by the export API. Copy Snapshot includes active custom columns and filtered saved rows using the existing report snapshot design. Version history records column definitions, custom values, cell corrections, and formatting; removing a column never deletes history. Run `python tests/browser_store_hours_sheet.py` for the standalone layout, column lifecycle, default-column protection, formatting persistence, filtered Excel, AA-and-beyond ranges, and mobile checks.

Run `python tests/browser_store_hours_autosave.py` for slow-network edits, failure/retry, persistent undo/redo, copy/cut outlines, row selection, historical dates, and mobile layout. Run `python tests/browser_store_hours_motion.py` for column shortcuts, default protection, animation, rapid navigation, zoom/resize alignment, and reduced motion. Run `python tests/browser_store_hours_styles.py` for fonts, border placement, uppercase names, saved styles, and Excel formatting. Run `python tests/browser_store_hours_scroll.py` for animated offscreen navigation, rapid direction changes, zoom, editor focus, manual scrolling, and reduced motion.

**Version history** opens a read-only, paginated before/after viewer using the current report filters. Migration `019_store_hours_versions.sql` captures employee review saves (including legacy review saves), manual employee additions/changes/removals, recurring schedule changes, and successful RT-POS import snapshots by store/date. Capture runs in the same database transaction as each change, so failed saves do not leave history. Identical schedule reuploads and source snapshots do not add redundant versions. Source snapshots use the RT-POS sync actor; review and workbook versions retain the acting user's ID and display name even if that account is later removed. Recurring schedule history is included across report dates. Current records were preserved as initial snapshots when tracking began; previously overwritten edits cannot be reconstructed.

The versions table has no cascading foreign keys and no portal mutation endpoint. Database privileges deny INSERT/UPDATE/DELETE/TRUNCATE to application-facing roles (service_role has SELECT only); security-definer capture functions write versions through triggers. An ALWAYS trigger rejects UPDATE, DELETE, and TRUNCATE, including through the current server connection. No retention job removes versions. These protections stop portal members, administrators, and ordinary application-role operations from changing or deleting versions. A database owner/superuser can still disable triggers, change the schema, or destroy the database; database-controlled history cannot prevent a privileged owner from overriding its protections. Undo changes drafts only; later saves append new versions rather than modifying history.

Migration `017_store_opening_closing.sql` stores time punches, per-day sync coverage, and legacy camera reviews separately. Migration `018_store_hours_employees_directory.sql` adds a persistent schedule directory, workbook previews, manual employees, and independent employee reviews while preserving legacy reviews. The importer reuses server-only `RTPOS_COOKIES` and downloads `https://myrtpos.com/newbdi/TimePunches.fwx`. Its first sync fetches the current month; later syncs include the last extracted `clockintime` date through today, retry failed days, and resume in seven-day batches. Each dealer has an isolated RT-POS session. The live export is CSV; legacy XLS and both AM/PM and 24-hour timestamp strings are supported. Older open shifts sometimes appear outside the requested range and are excluded by their clock-in date. A failed fetch preserves saved punches and marks coverage incomplete. A successful re-sync replaces punches in its date window without touching camera reviews or manual employees.

There is one row per unique employee/store/date. Employee names combine `name + " " + lastname`; comparison ignores capitalization and repeated whitespace. Multiple shifts use that employee's earliest clock-in and latest clock-out. A matching imported employee merges with their manual row. Missing stores show `-`, `No Clock In`, and `No Clock Out` until an employee is added. Dates and times from RT-POS retain the store's local wall time; Central time determines today's sync/date-filter boundary. Each employee has independent camera observations, revision checks, and chargebacks. Legacy store-level reviews are shown only on the first employee row.

The directory combines the active Calling Tree with all 38 stores from both sheets of `OPENING TIMING FOR ALL DEALERS.xlsx`, initially producing 55 stores across eight dealer groups. This includes The Fix, Smoke Magic, and the four ARBF Total Wireless stores, which are distinct from the five ARBF Metro stores. Workbook ARM WIRELESS maps to portal AMQ, including GLENVIEW to N1329B; TALKALOT WIRELESS / LEE ST maps to portal ARM / 317-002; SUPREME maps to SRH. Dropdown labels include these company names. The 11 supplemental stores have no connected RT-POS source and support manual employee entries.

To add future stores or dealers, use **Upload schedules**, choose an `.xlsx` file with the original **MON TO SAT** and **SUN** sheets, review the preview, and click **Apply workbook**. Preserve row 2 headings and list each store with the same carrier, company, market, and store name on both sheets. MON TO SAT columns E/F apply Monday-Friday and G/H apply Saturday; SUN E/F applies Sunday. Uploads add new stores and update matching schedules without deleting omitted stores or camera reviews. Reuploading the same workbook does not duplicate stores. New stores without an existing source mapping use manual employee rows. Files are limited to 2 MB and 5,000 stores; formulas, macros, duplicate stores, and invalid times are rejected. Connect Monday-Saturday opens at 10:00 AM, correcting workbook 10:00 PM values as confirmed by the user. Database schedules override the bundled `api/store_schedules.json` fallback.

Date-specific employee edits override workbook hours; clear an override and save to restore the default. Saving unchanged workbook hours with a camera review does not create an override. Recurring hours apply to existing and future report dates unless overridden. California and ARBF Metro have no supplied schedule. Camera observations alone determine compliance: missing camera times stay **Pending camera review** and missing scheduled times show **Schedule required**. RT punches never substitute for camera evidence. Late begins at exactly one minute after opening; early closing begins at exactly one minute before closing. A **-$10** charge applies separately to each late **Connect** employee at five minutes in **Houston/Reno** or ten minutes in **Dallas**. Pending charges remain unassessed rather than counting as $0. Discard stale edits and reload before retrying a revision conflict.

Run `python -m pytest tests/test_store_hours.py tests/test_store_schedules.py tests/test_store_hours_directory.py` for parsing, thresholds, imports, exports, validation, employee identity, workbook mapping, and access checks. Run `python tests/browser_store_hours.py` for the form, report, searchable filters, manual employees, workbook preview/apply, date selector, clipboard PNG, Excel, and mobile browser flow. Browser fixtures do not write production data.

## Account rest mode

On **Accounts**, only the permanent owner **Mahee** can click **Take a Rest** to pause an account and **Back to Work** to restore it. The permanent owner and the acting administrator's own account are protected. Rest differs from disabling: the user can authenticate, but only their session status and sign-out remain available; all protected report, export, account, upload and editing APIs reject access. Existing sessions detect changes every five seconds while visible, and when the tab regains focus. Returning to work restores access without another login.

The rest screen replaces the workspace, clears loaded report data and hides navigation. It shows the configured first-login message, then the eggplant message on the first reload in the same tab. The next three reloads show the three supplied images in attachment order, fitted to the screen without cropping. Further reloads keep the final image. Polling does not advance the sequence; a new rest episode or a fresh sign-in resets it. Migration `007_account_rest.sql` adds the persistent rest state; all accounts start with rest off. Run `python tests/browser_rest.py` to check the admin/user flow with simulated authentication.

## Quota Update

Open **Quota Update** in the sidebar. An administrator can expand **Manage monthly goals**, select a dealer and month, and download a template populated with that dealer's active Calling Tree stores. Enter goals, upload the workbook, review the preview, and click **Apply goals**. This replaces only that dealer's goals for the selected month. Members can view and export reports, but cannot upload goals.

The importer accepts the `spdi-ca` Goals layout (`Market`, `Stores`, `Voice`, `BTS`, `HSI/HINT`, `Acc`, optional `MIM`) and the new template with `Store ID`. Files must be `.xlsx` or `.xlsm`, at most 2 MB, with up to 5,000 rows. Macros are never executed. Formulas require cached results saved by Excel; otherwise replace formulas with values. Duplicate store rows are combined. Legacy files match market and store name within the selected dealer; Store ID is preferred and survives store renames. Unmatched or ambiguous stores are rejected before any data changes. Reports always follow the current Calling Tree, including after a replacement.

Migration `006_quota_update.sql` creates the private monthly goals tables automatically on production deployment. Actuals use the existing saved RT-POS imports, so the scheduled sales sync also updates quota progress without another download worker. Upload goals separately for each dealer; old SPDI portal goal data is not copied automatically.

ARBF accepts accessory goals and displays them in the Summary ACC GOALS column, including snapshots and Excel. Acc remains optional in older ARBF workbooks. ARBF overall score and rankings continue to use quota growth alone; accessory remaining, per-day goal and achievement stay hidden. Combined ACC GOALS totals include ARBF, while accessory achievement calculations use only the goals and sales of other dealers. Accessory actuals and trend include all dealers.

Calculations follow `spdi-ca`: Voice actual = new activations + reactivations - BTS - HSI; upgrades are excluded from Voice and Summary. The Upgrade table uses the saved `upgrade` metric, extracted from RT-POS `upgsor`, against the optional Upgrade workbook goal. Migration `011_quota_upgrade_goals.sql` adds storage for these goals, defaulting old uploads to zero. Total quota includes Voice, BTS, HSI and optional MIM goals; MIM actual is zero. Growth is actual / goal. Accessory trend is actual / elapsed days * days in month; per-day goal is remaining accessories / remaining days after today. Projected accessory achievement is trend / accessory goal. Overall average is the average of quota growth and projected accessory achievement. Zero denominators produce zero. Central time determines elapsed days. Past months use all their days, while future months have zero actuals and elapsed days. Rankings restart per dealer and market with competition ties (1, 1, 3). Totals use aggregate goals and actuals, not an average of store percentages.

The page includes Voice, BTS, HSI/HINT, Upgrade and achievement-summary tables, month/dealer/market/store filters, five-sheet Excel export and individual PNG snapshots. Snapshot images are 1920 pixels wide with height fitted to their contents, and omit the Dealer column. Select at most 350 stores per snapshot; Excel includes all filtered stores. Missing sales show a dash; partial or stale actuals, totals and rankings are labeled provisional.
