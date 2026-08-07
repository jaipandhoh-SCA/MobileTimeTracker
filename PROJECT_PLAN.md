
# ADU Portal — Working Plan

> My living plan + changelog. Planning happens here; approved items get handed to Claude Code to build. Updated every time a change ships.

**Last updated:** 2026-07-21 (Light Soft UI redesign shipped)

---

## 1. How this doc works

- **Backlog** — ideas and changes not started yet.
- **Active** — what's being planned or built right now (hand these to Claude Code).
- **Changelog** — what's shipped, newest first, with dates.
- **Decisions** — choices made and the reason, so we don't relitigate them.

Rule: nothing goes to Claude Code until it's written under **Active** with enough detail to build.

---

## 2. Active (planning / in progress)

> **Direction:** Channel performance dashboard for ADU sales. Time tracking removed. GoHighLevel + Meta Ads integrated. Neon (database) + Google OAuth (own credentials) + Cloudflare R2 (files).
>
> **Current codebase:** `main.py` (entry), `app.py` (factory), `models.py` (8 models: User, LeadSource, Client, ClientActivity, PropertyImage, ClientStatusChange, ChannelSpend, AuthorizedUser), `routes.py` (~2100 lines), `google_auth.py` (Google login), `r2_storage_helper.py` (Cloudflare R2), `ghl_helper.py` (GoHighLevel API), `meta_ads_helper.py` (Meta Ads API), `utils.py` (TZ/date helpers).

_No items currently active. See Backlog for next candidates._

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

- ~~**Run `migration_phase_a.sql` against Neon**~~ — removed; time-tracking tables were resurrected and hold live data. Use Alembic for future schema changes.
- **Hosting** — decide where the app runs off Replit (Render, Railway, Fly.io, or self-hosted). Set env vars/secrets there; configure the OAuth redirect URI to match the new domain.
- **Replit cleanup** — remove `.replit`, `replit.nix`, and any Replit-specific config once the app is confirmed running elsewhere.
- **Google Maps** — decide whether to keep the Maps embed (needs an API key) or switch address links to a plain `maps.google.com?q=` URL (no key). Minor.
- **Google Ads API** — auto-import Google Ads spend (same pattern as Meta Ads). Deferred from Phase C.
- **Scheduled syncs** — auto-run GHL contact sync and Meta spend sync on a cron/schedule instead of manual button press.

---

## 4. Changelog

### 2026-07-22 — Resurrect Time Tracking & Payroll

**Scope:** Brought back clock in/out, manual time entry, My Logs, and payroll — all removed in Phase A (commit `218e3ab`). No PDF/CSV exports restored (intentionally dead). Old data unrecoverable (Neon PITR window passed); tables recreated empty.

**Models:** Added `TimeEntry` and `ActiveClock` to `models.py`. Added `hourly_rate` column to `User` and `AuthorizedUser` (with auto-migration in `app.py`). Added relationships on `User` and `Client`.

**Routes (routes.py):**
- Clock: `/clock/start`, `/clock/status` (JSON polling), `/clock/break15`, `/clock/lunch`, `/clock/stop`
- Time entry: `/quick-log` (manual entry), `/my-logs` (personal log viewer)
- Payroll (supervisor): `/admin` (payroll dashboard), `/admin/rep/<id>/entries`, `/admin/entry/<id>/edit`
- Updated `/edit-user-profile` and `/add-authorized-user` to handle `hourly_rate`
- Added `format_hours` Jinja filter

**Helpers (utils.py):** `round_to_quarter_hour`, `calculate_duration`, `format_hours`, `get_pay_period_dates`, `get_next_pay_period_dates`, `get_previous_pay_period_dates`, `get_last_30_days_dates`, `get_month_to_date_dates`.

**Templates (all new, styled to DESIGN.md):** `stop_clock.html`, `quick_log.html`, `my_logs.html`, `admin_dashboard.html`, `rep_time_entries.html`, `edit_entry.html`. Updated: `base.html` (nav links), `home.html` (Alpine.js clock card), `edit_profile.html`, `edit_user_profile.html`, `manage_users.html`.

**Auth:** `google_auth.py` copies `hourly_rate` from `AuthorizedUser` on first login.

**Migration:** `migration_resurrect_time_tracking.sql` — additive only (CREATE TABLE IF NOT EXISTS, ADD COLUMN with existence checks). Run manually via Neon console.

**Infrastructure:** Added `scripts/backup_db.sh`, added `backups/` to `.gitignore`, removed dead `reportlab` dependency from `pyproject.toml`.

**Tested:** Full clock flow (clock in → break → lunch → stop → entry created), manual quick-log, My Logs view, payroll dashboard, rep entries, entry edit, hub clock card, empty states, Pacific time display, quarter-hour rounding. All 7 test groups passed.

### 2026-07-21 — Honest Empty States for Dashboard

**Channel cards always render.** Replaced the old behavior (cards hidden when no data) with 6 canonical channels that always appear: Organic, Meta Ads, Google Ads, Calls, CRM pipeline, Referral. Each card shows one of three states based on real integration status.

**"Not connected" state:** Cards whose integration isn't configured (env vars missing) show "Not connected" with a muted label, flat placeholder line instead of sparkline, em-dashes for stats, and a "Connect" link to `/settings/integrations`.

**"No data yet" state:** Cards whose integration IS connected but has no spend/leads for the current period show em-dashes and "No data yet" — visually distinct from "Not connected."

**Summary card:** When no ad platforms are connected, ROI hero shows "Connect your data sources to see ROI" linking to integrations. Revenue/Ad spend/Leads/Conversion show em-dashes when no real data. ROI is never computed from incomplete spend data.

**Sync pill:** Reflects real connection state. Shows "Not connected" with link when nothing is configured. When connected, lists only actually-connected service names with real last-sync time.

**Backend:** New `_get_integration_status()` helper checks env vars. `_build_channel_cards()` rewritten: uses `CANONICAL_CHANNELS` list with `requires` field mapping to integrations, maps lead sources to channels via name patterns, returns `connected` and `has_data` flags per card.

**Verified:** Full integration test with empty database — all 6 cards render in "Not connected" state, no fake numbers, no errors. Seed route (`/settings/lead-sources/seed`) left intact (guarded, intentional for initial setup).

### 2026-07-21 — Light Soft UI Redesign

**Full frontend theme replacement.** Replaced the dark futuristic theme (near-black surfaces, mint green primary, glow shadows, scan-line textures) with a light "soft UI" design system.

**DESIGN.md rewritten** as single source of truth. New spec: light gray canvas (#f3f4f6), white cards with soft diffuse shadows (no borders, no glows), system font stack (Fraunces removed), strict 4-color accent discipline (near-black default, magenta #D6246E brand accent, green #10b981 positive, red #ef4444 negative).

**Hub page restructured** to match target mobile design: breadcrumb top bar, sync-status pill, summary card with Overall ROI hero number + headline stats (Revenue/Ad spend/Leads/Conversion), channel cards grid with per-channel sparkline charts (color-coded: green for no-spend, magenta for Meta, near-black for Google/CRM, slate for Calls), empty/zero states. Responsive: single-column mobile, 2-across tablet, 3-across desktop.

**Tailwind config overhauled** in base.html: removed 5-level surface system, edge borders, glow shadows, Fraunces font import. New tokens: canvas, card, hairline, pill, txt (primary/secondary/muted), accent, pos, neg.

**Templates restyled (15):** base.html, home.html, landing.html, clients.html, client_form.html, edit_profile.html, edit_user_profile.html, manage_users.html, integrations_settings.html, lead_sources_settings.html, lead_source_backfill.html, channel_spend.html, roi_report.html, 403.html, access_denied.html. Every dark-theme class removed; no page retains old styling.

**No backend changes.** Templates, CSS tokens, and Chart.js config only.

### 2026-07-20 — Phase C: GoHighLevel + Meta Ads Integrations

**GoHighLevel contact sync:** New `ghl_helper.py` — API v2 client that fetches contacts, paginates, and maps GHL fields to `Client` model. Sync imports all GHL contacts as CRM leads, skipping duplicates via new `Client.ghl_contact_id` column (unique, indexed). Tags mapped to status (e.g. "prospect" → Prospect). `ClientStatusChange` logged for each import.

**Meta Ads spend sync:** New `meta_ads_helper.py` — Meta Marketing API v21.0 client. `fetch_monthly_spend()` pulls total spend, leads, impressions, clicks for a month. `fetch_campaign_breakdown()` returns per-campaign detail. Sync upserts a `ChannelSpend` entry for the current month against the mapped lead source.

**Integrations settings page:** `/settings/integrations` (supervisors). For each service: connection status badge, env var checklist (set/missing), test connection button, sync button, lead source mapping dropdown. Meta section shows campaign breakdown table when connected. Help section explains the workflow.

**Routes added (7):** `integrations_settings`, `ghl_test_connection`, `save_ghl_lead_source`, `ghl_sync_contacts`, `meta_test_connection`, `save_meta_lead_source`, `meta_sync_spend`.

**Model change:** `Client.ghl_contact_id` (VARCHAR(100), unique). Auto-migration in `app.py`.

**Nav:** "Integrations" link added to profile dropdown (supervisors). Settings highlight updated.

**New env vars:** `GHL_API_KEY`, `GHL_LOCATION_ID`, `META_ADS_ACCESS_TOKEN`, `META_ADS_ACCOUNT_ID`.

### 2026-07-20 — Phase B: Channel Performance Cards on Hub

**New dashboard section:** "Channel Performance" (Section 2, between This Week and Needs Attention). Collapsible, supervisors only, shows per-channel cards for the current month. Each card: source name, channel type badge (color-coded — amber for paid ads, green for organic, blue for referral), 3-column metric grid (spend, leads with MoM delta, CPL), revenue/ROI/won footer. Links to full ROI report. Only sources with spend or leads this month appear.

**Route change:** `home()` now calls `_build_channel_cards()` helper for supervisors. Queries `ChannelSpend` for current month spend, `Client` for leads/revenue created this month and last month per source. Cards sorted by highest spend.

**Template:** `home.html` Section 2 added. Alpine.js `channels` toggle added to `hubSections()` with localStorage persistence. Section numbering updated (Needs Attention → 3, Pipeline → 4, Activity → 5).

### 2026-07-20 — Phase A: Remove All Time-Tracking Code

**Stripped time tracking** from the entire codebase. The app is now a channel performance dashboard, not a time tracker.

**Models deleted:** `TimeEntry`, `ActiveClock`. **Columns removed:** `User.hourly_rate`, `AuthorizedUser.hourly_rate`, `User.time_entries` relationship, `User.active_clock` relationship, `Client.time_entries` relationship.

**Routes deleted (~1000+ lines):** `start_clock`, `clock_status`, `take_break_15`, `take_lunch`, `stop_clock`, `quick_log`, `my_logs`, `admin_dashboard`, `edit_entry`, `rep_time_entries`, `export_csv`, `generate_time_entries_pdf`, `export_rep_time_entries_pdf`, `export_my_logs_pdf`, `update_user_rate`, `format_hours_filter`. Clock/pay-period logic removed from `home()`, `edit_profile()`, `edit_user_profile()`, `add_authorized_user()`, `remove_user()`.

**Templates deleted (6):** `stop_clock.html`, `quick_log.html`, `my_logs.html`, `admin_dashboard.html`, `edit_entry.html`, `rep_time_entries.html`. Remaining templates cleaned: `home.html` (clock section, hours stats, weekly chart removed), `base.html` (shift indicator, clock_status fetch, time-tracking nav links removed), `edit_profile.html` (hourly_rate fields removed), `edit_user_profile.html` (hourly_rate field removed), `manage_users.html` (hourly_rate column/form removed), `landing.html` ("Time Tracking" → "Channel ROI" feature card).

**Utils stripped:** Removed `calculate_duration`, `round_to_quarter_hour`, `format_hours`, all `get_*_period_dates` helpers. Kept timezone and date formatting only.

**Migration script:** `migration_phase_a.sql` was removed — time-tracking tables were later resurrected with live data. Schema changes now use Alembic.

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
