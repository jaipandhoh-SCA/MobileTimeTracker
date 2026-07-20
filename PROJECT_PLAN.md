
# ADU Portal — Working Plan

> My living plan + changelog. Planning happens here; approved items get handed to Claude Code to build. Updated every time a change ships.

**Last updated:** 2026-07-16 (Neon DB + own Google login + R2 object storage; keep all .md files)

---

## 1. How this doc works

- **Backlog** — ideas and changes not started yet.
- **Active** — what's being planned or built right now (hand these to Claude Code).
- **Changelog** — what's shipped, newest first, with dates.
- **Decisions** — choices made and the reason, so we don't relitigate them.

Rule: nothing goes to Claude Code until it's written under **Active** with enough detail to build.

---

## 2. Active (planning / in progress)

> **Direction:** Self-owned, off Replit. Neon (database) + **Google login with our own OAuth credentials** + S3-style object storage (Cloudflare R2) for files. Google is used **only for login**, not storage. Three items below, in build order.
>
> **⚠️ Critical path:** The app currently **crashes on startup** — `google_auth.py` (line 20) references `REPLIT_DEV_DOMAIN`, which no longer exists. It won't run until item B fixes that line. So do **A + B together** to get it booting on Neon, then **C** for files.
>
> **Known codebase (from Claude Code audit, 2026-07-16):** `main.py` (entry), `app.py` (factory: SQLAlchemy/CSRF/Flask-Login), `models.py` (7 models: User, Client, TimeEntry, ActiveClock, ClientActivity, PropertyImage, AuthorizedUser), `routes.py` (~2170 lines, all live), `google_auth.py` (Google login — keep, remove Replit lines), `google_drive_helper.py` (Drive — to be replaced with R2), `utils.py` (TZ/pay-period helpers). 16 templates, all in use.

### A. New Postgres database on Neon
- **Goal:** Own the database directly; drop Replit's provisioned DB.
- **Decision:** No data migration needed (Replit DB had no significant data). Start fresh.
- **Scope:**
  - Create a new **Neon** project at neon.com (region: US West for a Pacific-time team).
  - Copy the connection string; set `DATABASE_URL` in the app's environment.
  - Let SQLAlchemy create the schema from the models (empty tables), or run migrations if set up.
- **Acceptance:** App boots against Neon, tables exist, first account becomes Supervisor (see item B for how that account is created now).
- **Status:** ready for Claude Code

### B. Google login on our own OAuth credentials (off Replit)
- **Goal:** Keep Google sign-in, but authenticate with **our own** Google Cloud OAuth client instead of Replit's — and fix the `REPLIT_DEV_DOMAIN` line that crashes startup.
- **Keep as-is:** `google_auth.py` stays. The allowlist (`AuthorizedUser`) still gates access, and "first user to sign in becomes Supervisor" is unchanged. No email/password, no registration route, no password reset to build.
- **Google Cloud setup:**
  1. Google Cloud Console → create a project (login only; no Drive API needed).
  2. Configure the **OAuth consent screen** (External; add users/test users as needed).
  3. Create an **OAuth Client ID** (Web application). Add authorized redirect URIs for both local dev (`http://localhost:5000/google_login/callback`) and production (`https://<your-domain>/google_login/callback`).
  4. Store `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` as env vars.
- **Code changes in `google_auth.py`:**
  - Replace the `DEV_REDIRECT_URL` line (20) that uses `REPLIT_DEV_DOMAIN` with a redirect URL from config/env (or derived from the request), so it no longer crashes.
  - Remove the Replit-docs print block (lines 23–36).
  - Confirm it reads client creds from `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET`.
- **Acceptance:** App boots on Neon with no Replit env vars, Google sign-in works end-to-end via our own OAuth client, allowlist still gates access, first sign-in creates the Supervisor.
- **Status:** ready for Claude Code

### C. Replace Google Drive with S3-style object storage (Cloudflare R2)
- **Goal:** Store property images, documents, and contracts in an S3-compatible bucket instead of Google Drive.
- **Why R2:** S3-compatible (use `boto3`), generous free tier, no egress fees. AWS S3 or Backblaze B2 also work — same code, just a different endpoint.
- **Scope:**
  - **Replace `google_drive_helper.py`** with an R2/`boto3` helper (same function surface: create-prefix, upload, download, delete). Everything in the file except the Replit `get_drive_credentials()` was generic, but we're swapping the whole backend from Drive to S3, so rewrite it.
  - Update `routes.py` Drive upload calls and the `PropertyImage` model + `ClientActivity` attachment handling to use the new helper.
  - Create a Cloudflare R2 bucket; get account ID, access key, secret, bucket name, endpoint.
  - Store `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`, `R2_ENDPOINT` as env vars.
  - **Folders → key prefixes:** object storage is flat. Recreate the structure as key prefixes, e.g. `property-files/{client-name-address}/property-images/{filename}`, `.../documents/...`, `.../contracts/...`.
  - **Serving/sharing files:** generate **presigned URLs** (time-limited) so files stay private but display in the app. Use a public bucket + custom domain only if permanent public links are actually needed.
  - Keep existing file-type and size validation (images ≤16MB, etc.).
- **Acceptance:** Uploading an image/document/contract puts the object in R2 under the right prefix, it displays/downloads in the app via presigned URL, delete works, and `google_drive_helper.py`'s Drive/Replit code is gone.
- **Status:** shipped (2026-07-16)

### Also: Google Maps
- Minor. Property addresses currently use Google Maps. Simplest de-Google option: link out to `https://www.google.com/maps?q={address}` (no API key, no dependency) or switch the embed to OpenStreetMap. Low priority — decide during item C or leave as-is.

<!-- Template for each item:
### [Short title]
- **Goal:** what problem this solves
- **Scope:** what changes (pages, models, routes)
- **Acceptance:** how we know it's done
- **Notes/questions:** open items
- **Status:** planning | ready for Claude Code | building | testing
-->

---

## 3. Backlog

- **Hosting** — decide where the app runs off Replit (Render, Railway, Fly.io, or self-hosted). Set env vars/secrets there; configure the OAuth redirect URI to match the new domain.
- **Replit cleanup** — remove `.replit`, `replit.nix`, and any Replit-specific config once the app is confirmed running elsewhere. Migrate any secrets that lived in Replit's vault into the new host's env.
- **Google Maps** — decide whether to keep the Maps embed (needs an API key) or switch address links to a plain `maps.google.com?q=` URL (no key). Minor.

---

## 4. Changelog

### 2026-07-19 — Full Channel ROI Report

**New report page** at `/reports/roi` (supervisors). Answers "which marketing channel deserves more budget?" with first-touch attribution (clients counted in the period they were created).

**Features:** Date range picker with presets (last month default, this month, last 3 months, YTD, custom). Headline sentence ("Every $1 spent on [best channel] returned $X.XX"). Table per source: spend, leads, CPL, won (Active+Completed), close rate, revenue (closed + projected, labeled), ROI multiple. Sources with $0 spend still appear (referrals, organic) with revenue visible and ROI shown as "---". Per-source funnel expansion (Lead/Prospect/Active/Completed/On Hold/Lost counts + color bar). Comparison deltas vs previous equal-length period. CSV export. Attribution rule noted on page.

**Routes added:** `/reports/roi`, `/reports/roi/export`. Helper functions `_parse_roi_dates()`, `_build_roi_rows()`.

**Template:** `roi_report.html` rewritten (was a placeholder days-to-close page). Updated `base.html` nav highlights to include `roi_report`.

### 2026-07-19 — Journey Timeline + Days-to-Close ROI

**New model:** `ClientStatusChange` (client_id, from_status, to_status, changed_by_user_id, changed_at). Logged on every status change (AJAX update, edit form save, and initial creation). Table auto-created by `db.create_all()`.

**Journey timeline:** Replaced the flat "Recent Activities" list on the client detail page with a vertical timeline merging all events chronologically: lead created (with source badge + detail), every status change with elapsed time ("12 days as Lead"), activities (type-specific icons, notes, attachments, next steps), file uploads, and deal closed (final contract value). Header shows total deal age and current stage duration. Events beyond 6 are collapsed with expand/collapse toggle via Alpine.js.

**ROI report — days-to-close:** Added "Avg Days to Close" column to the existing Channel ROI report (`/reports/roi`). Shows average days from lead creation to Completed status per lead source, using `ClientStatusChange` records. Only displayed for sources with 5+ closed clients; sources below threshold show "N/5 closed" hint. Added to both table view and CSV export. Computed in `_build_roi_rows()`.

**Routes modified:** `update_client_status`, `edit_client` (POST), `create_client` — all now log `ClientStatusChange`. `edit_client` (GET) builds timeline data via `_build_client_timeline()` helper.

### 2026-07-19 — Global Search
Added search bar in the nav (visible on Hub, Clients, Reports, Settings). Searches clients (name, address, contact_name) and activities (note_text) by substring, case-insensitive. Results grouped by type (Clients / Activities) in a dropdown with keyboard navigation (arrow keys + Enter). Press `/` to focus from anywhere. Mobile: search input in the hamburger menu. New route: `/api/search?q=` (JSON, returns max 10 per type). Debounced input with `AbortController` to cancel stale requests.

### 2026-07-19 — Needs Attention section rebuild
Rebuilt the hub's "Needs Attention" section (Section 2) from a basic overdue/stale list into a unified, prioritized feed. Four trigger rules: (1) overdue next step date, (2) no next step set at all, (3) stale client — no activity in 14+ days (amber) / 28+ days (red), (4) missing lead source. Thresholds are config values (`STALE_AMBER_DAYS`, `STALE_RED_DAYS` in `app.py`). Items sorted red-first, then by days desc. Each row shows client name, what's wrong, days count, and two inline actions: "Add next step" (opens inline form with type + date, posts to new `quick_add_next_step` route) and "Log activity" (links to client page anchored at activity form). Supervisors see a per-rep count summary at the top ("Mike: 3 · Sarah: 1"). If nothing needs attention, shows a warm "All caught up" message. Multiple issues per client are merged into a single row.

### 2026-07-18 — Weekly Brief Hub Overhaul

**Design overhaul:** Replaced warm-palette daily clock UI with dark futuristic theme. Forest green primary (`#34D399`), 5-level surface system (`#0B0F14` → `#253344`), cool-tinted text hierarchy, scan-line texture overlay. New typography: Fraunces (display) + Inter (body). Nav shrunk to 4 items: Hub, Clients, Reports, Settings. Created `DESIGN.md` with full token reference.

**Hub restructure (`home.html`):** Replaced daily time-clock homepage with 5-section weekly brief:
1. **This Week** — rich brief with new leads (source breakdown, WoW delta), pipeline movement (status-change pills with client names), deals closed (revenue, WoW delta), follow-up debt count, hours logged (WoW delta), and weekly bar chart.
2. **Needs Attention** — overdue follow-ups + stale clients with action buttons.
3. **Pipeline** — collapsible status grid with filtered client list.
4. **Recent Activity** — collapsible feed.
5. **Time** — compact clock in/out + pay period total.

**Route changes (`routes.py`):** `home()` expanded with Mon–Sun Pacific week boundaries, lead source breakdown via `joinedload`, pipeline movement via `ClientActivity.activity_type == 'Status Change'`, follow-up debt (overdue steps + no-next-step subquery), WoW deltas for leads/deals/hours. `update_client_status()` now logs Status Change activities to `ClientActivity`.

**Templates:** `base.html` rewritten (dark theme Tailwind config, Alpine.js collapse plugin, 4-item nav). `landing.html` restyled to match. `home.html` completely rewritten as weekly brief hub. Remaining templates not yet propagated.

### 2026-07-18 — Channel Spend + Revenue Capture

**Feature A — Channel Spend (supervisors):** New `ChannelSpend` model (id, lead_source_id FK, amount, period_month, note, created_by). Page at `/reports/channel-spend` with month picker, add/edit/delete entries, per-source totals. Any lead source can have spend (ads, referral fees, etc.). Template uses Alpine.js for inline edit toggle.

**Feature B — Revenue capture at close:** Added `Client.final_contract_value` (decimal, nullable). When status changes to "Completed", a modal prompts for the final contract value (can skip). Both values shown on client page: "Estimated Value" (opportunity_value, the pipeline estimate) and "Final Contract Value" (the actual closed amount). Final value is editable inline with auto-save.

**Routes added:** `/reports/channel-spend` (list + add), `/reports/channel-spend/<id>/edit`, `/reports/channel-spend/<id>/delete`, `/clients/<id>/update_final_value`.

**Templates:** New `channel_spend.html`. Updated `client_form.html` (completion modal, final value field, label change to "Estimated Value"). Updated `base.html` (Reports nav highlight includes channel_spend).

### 2026-07-18 — Lead Source Tracking

**New model:** `LeadSource` (id, name, channel_type enum, is_active). Seeded with 10 defaults: Google Ads, Meta Ads, Instagram Organic, Facebook Organic, Website / SEO, Phone Call, Referral — Client, Referral — Partner, Repeat Client, Other.

**Client model:** Added `lead_source_id` (FK, nullable) and `source_detail` (optional free text).

**Routes added:** `/settings/lead-sources` (manage sources — add, rename, deactivate), `/settings/lead-sources/seed`, `/settings/lead-sources/backfill` (supervisor page to assign sources to existing clients), `/api/missing-lead-source-count`.

**Client create form:** Lead Source is now required (dropdown of active sources + optional detail field). Edit form: same fields, optional.

**Templates:** `lead_sources_settings.html`, `lead_source_backfill.html`. Updated `client_form.html` (source badge in view mode, dropdown in edit mode and create form), `clients.html` (source badge on each row), `home.html` (dismissible banner for missing sources).

**Auto-migration:** `app.py` adds `lead_source_id` and `source_detail` columns if missing.

### 2026-07-16 — Item C shipped: Google Drive → Cloudflare R2
**Deleted `google_drive_helper.py`** (entire file — Replit connector + Drive API). Replaced with **`r2_storage_helper.py`** using `boto3` (S3-compatible): `upload_file`, `download_file`, `delete_file`, `generate_presigned_url`, `build_client_prefix`.

**Models:** Client's 4 `gdrive_*` folder ID columns → single `storage_prefix` column. PropertyImage's `gdrive_file_id` + `gdrive_web_view_link` → single `storage_key` column.

**Routes (`routes.py`):** All 6 upload/download/delete touchpoints rewritten to use R2. Key structure: `property-files/{sanitized-name}/property-images|documents|contracts/{timestamp_filename}`. Activity attachments store R2 key in `file_path`; download route generates presigned URL. Removed `fix_folder_permissions` route (Drive-only concept).

**Template (`client_form.html`):** Removed 3 "Open in Drive" folder link buttons and updated description text.

**Deps (`pyproject.toml`):** Removed `google-api-python-client`, `google-auth-httplib2`, `google-auth`. Added `boto3`.

**New env vars needed:** `R2_ENDPOINT`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET`.

### 2026-07-16 — Cleanup + Items A & B shipped
**Cleanup:** Deleted 10 macOS `._*` files, `__pycache__/`, and the dead correction-notes route block from `routes.py`. Renamed pyproject.toml project to `all-inclusive-adu-portal`. Created `CLAUDE.md` for session context. All `.md` files kept.

**Item A (Neon DB):** Added `python-dotenv` loading to `app.py` (reads `.env.local` then `.env`). Neon project `mute-meadow-17717447` connected — `DATABASE_URL` in `.env.local` (gitignored). SQLAlchemy `db.create_all()` in `app.py` creates schema on boot.

**Item B (Own Google OAuth):** Removed `DEV_REDIRECT_URL = f'https://{os.environ["REPLIT_DEV_DOMAIN"]}/...'` (line 20) and the Replit-docs print block (lines 23-36) from `google_auth.py`. The OAuth flow already derived redirect URIs dynamically from `request.base_url`, so no replacement variable was needed. Reads creds from `GOOGLE_OAUTH_CLIENT_ID` / `GOOGLE_OAUTH_CLIENT_SECRET` (unchanged). AuthorizedUser allowlist and first-user-becomes-supervisor behavior untouched.

**Remaining Replit code:** `google_drive_helper.py` still has `get_drive_credentials()` using Replit connector — will be replaced entirely in Item C (R2).

### 2026-07-16 — Codebase audit + cleanup approved
Claude Code inventoried the repo. No orphan templates or modules. **Keep all `.md` files** (`replit.md`, `walkthrough.md`, `README.md`). Approved for deletion (List A): macOS `._*` files (9) + `.___pycache__`, `__pycache__/`, and the commented-out correction-notes route (`routes.py:444–463`). List B: `google_auth.py` is **kept** but has its Replit lines removed (item B); `google_drive_helper.py` is replaced with R2 (item C); `pyproject.toml` renamed `repl-nix-workspace` → `all-inclusive-adu-portal`. Consider adding `CLAUDE.md` (or committing this plan) to the repo for standing context.

<!-- Template:
### YYYY-MM-DD — [Short title]
What changed and why. Any follow-ups.
-->

---

## 5. Decisions

- **2026-07-16 — Fresh database, no migration:** Replit DB held no significant data, so we start clean rather than migrating. New Postgres on **Neon (direct)** — same engine as before, so no code changes beyond `DATABASE_URL`.
- **2026-07-16 — Keep Google for login only; drop Google Drive:** Reps sign in with Google (via our **own** OAuth credentials, not Replit's). File storage moves off Google Drive to **Cloudflare R2** (S3-style). Login and storage are independent, so we get Google sign-in without any Google Drive dependency. Database stays on **Neon**. _(Supersedes the earlier "drop Google entirely / email+password" note — Jai confirmed Google login is required.)_

<!-- Template:
- **YYYY-MM-DD — [Decision]:** what we decided and why.
-->
