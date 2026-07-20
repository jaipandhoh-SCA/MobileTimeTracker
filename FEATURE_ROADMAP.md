# ADU Portal — Feature Roadmap

> The extensive build plan. Each item is written to be handed to Claude Code as-is. Work top-down within a phase; phases are ordered by value-per-effort. Companion to `PROJECT_PLAN.md` (which tracks what's active/shipped — move items there as you start them).

**Design north star:** a warm, professional trade tool. **Usage model: a weekly brief, not a daily app** — people open it Monday morning to see how the business is going, then dip in during the week to update clients. Design for that rhythm.

**Structural rules (from Jai, 2026-07-17):**
1. **Mostly one page.** The app lives on a single hub page with sections you scroll/expand — not a maze of nav links. Deep pages exist only where a workflow truly needs its own screen (client detail, payroll admin).
2. **Clock-in is de-emphasized, not featured.** Keep it working, but it gets a compact corner, not the hero position. It may be removed entirely later — build nothing new that depends on it.
3. **The Weekly Scoreboard is the heart of the app** — the thing people actually come to read.

---

## Phase 0 — Design System (do first; everything else inherits it)

### 0.1 Visual identity: "Warm Professional"
- **Goal:** A distinct, consistent look that doesn't read as a default Tailwind/AI build.
- **The anti-generic rules (give these to Claude Code verbatim):**
  - **No default indigo/violet.** Palette anchored in warm construction neutrals: warm off-white background (e.g. `#FAF7F2`-family), deep charcoal-brown text, one earthy primary (terracotta/clay or deep forest green), one warm accent (amber/ochre) for highlights. Status colors keep meaning (green/amber/red) but tuned warm.
  - **Typography does the branding.** A characterful display face for page titles and big numbers (e.g. a slab or humanist serif like Zilla Slab, Bitter, or Fraunces via Google Fonts), a clean sans (e.g. Inter or Source Sans 3) for body/UI. Big numbers get the display face — payroll totals, hours, ROI figures should feel like a well-set ledger.
  - **Cards, but not card soup.** Fewer, larger panels with clear hierarchy instead of grids of identical rounded boxes. Use section headers with rules/dividers, not floating cards for everything.
  - **No gradient-on-everything, no glassmorphism, no emoji-as-icons.** One consistent icon set (Lucide or Heroicons outline), used sparingly.
  - **Texture over gloss:** subtle warm shadows, 1px borders in warm gray, generous whitespace. Density increases on supervisor/report pages, breathes on rep/mobile pages.
- **Scope:** Define CSS variables (colors, type scale, spacing, radii) in `base.html`; restyle nav + one template as the reference implementation; document the tokens in a `DESIGN.md`.
- **Acceptance:** Two pages fully on the new system; `DESIGN.md` exists so every later feature uses the same tokens; side-by-side with the old look reads as a different, more grown-up product.

### 0.2 The one-page hub
- **Goal:** Nearly everything lives on a single scrolling hub. Open the app Monday → read the week → act on what needs acting. Minimal nav.
- **Scope:**
  - **Section order on the hub (top to bottom):**
    1. **This Week** — the weekly scoreboard (see 3.1, promoted to the front): leads by source, pipeline movement, deals closed + revenue, follow-up debt. Plain-language sentences.
    2. **Needs Attention** — overdue next steps, stale leads, clients missing a source. Action buttons inline (complete/reschedule/assign) — fix things without leaving the page.
    3. **Pipeline** — opportunities by stage, collapsible; click a client → client detail (one of the few real sub-pages).
    4. **Recent Activity** — latest logged activities, collapsible.
    5. **Time** (compact, bottom or corner) — clock in/out + pay-period total for those who use it. Small by design; may be removed later, so nothing else on the page depends on it.
  - Supervisors see company-wide data with a rep filter; reps see their own. Same page, same order.
  - **Nav shrinks to:** Hub · Clients · Reports (ROI + payroll) · Settings. That's it.
  - Sections collapse and remember state (per user); every stat drills into its section rather than a separate page where possible.
  - Empty states always say *what to do next*, never just "no data."
- **Acceptance:** A supervisor's Monday review happens entirely on one page; total nav destinations ≤ 4; clock-in occupies < 10% of the screen.

---

## Phase 1 — Marketing Attribution & ROI (the Hyros-inspired core)

*What we're borrowing from Hyros (the parts proven to work): every dollar of revenue tied to a source, channel-level ROI, customer journeys visible on a timeline, and long/delayed sales cycles handled. What we're deliberately skipping for v1: anonymous visitor tracking, ad-platform API feedback loops, AI forecasting.*

### 1.1 Lead source on every client
- **Goal:** Nothing enters the funnel without knowing where it came from.
- **Scope:**
  - New model `LeadSource` (name, channel type, active flag) — seeded with: Google Ads, Meta Ads, Instagram Organic, Facebook Organic, Website/SEO, Phone Call, Referral — Client, Referral — Partner, Repeat Client, Other. Supervisors can add/edit sources in a settings page.
  - `Client.lead_source_id` (required on create), plus optional free-text `source_detail` ("referred by the Hendersons", "called from yard sign").
  - Backfill UI: a supervisor page listing clients with no source, quick-assign dropdowns.
  - Source shown as a badge on client cards/pages.
- **Acceptance:** New clients require a source; existing clients backfillable in bulk; source visible everywhere a client appears.

### 1.2 Channel spend tracking
- **Goal:** Record what each channel costs so ROI is real, not vibes.
- **Scope:**
  - New model `ChannelSpend`: lead_source_id, amount, period (month), optional note. Manual entry by supervisors — one small form, takes 2 minutes a month.
  - Handles non-ad costs too: referral fees, sign printing, website hosting — anything with a receipt.
  - Monthly spend list view with edit; totals per channel per month.
- **Acceptance:** A supervisor can log "Google Ads — March — $2,400" in under 30 seconds; spend shows in the ROI report (1.4).

### 1.3 Revenue capture at close
- **Goal:** Know actual revenue per client, not just estimated opportunity value.
- **Scope:**
  - `Client.final_contract_value` — prompted when status moves to Completed (opportunity value stays for the pipeline).
  - Optional lightweight payment tracking later (backlog): deposits/progress payments.
- **Acceptance:** Completed clients carry a real revenue number; the ROI report uses actuals for Completed, opportunity value for Active (clearly labeled as projected).

### 1.4 Channel ROI report — the money page
- **Goal:** One page a business owner reads monthly: what each channel costs, what it returned.
- **Scope:**
  - Per channel per period: spend, leads, cost-per-lead, clients won, close rate, revenue (actual + projected), ROI multiple.
  - Date range picker aligned to months; comparison vs. previous period (▲▼ with plain-language deltas).
  - One honest headline stat at top: "Every $1 spent on [best channel] returned $X."
  - Funnel view per channel: leads → prospects → active → completed (where sources leak).
  - CSV export.
- **Acceptance:** The report answers "which channel should get more budget next month?" without opening anything else.

### 1.5 Client journey timeline
- **Goal:** Hyros-style journey view, powered by data you already have.
- **Scope:**
  - On the client page: a vertical timeline merging status changes, activities, images/files uploaded, next steps — from lead-in (with source badge) to close.
  - Show elapsed time between stages ("Lead → Prospect: 12 days") and total age of the deal.
  - Surface stage-duration averages on the ROI report ("Google Ads leads close in avg 45 days; referrals in 28").
- **Acceptance:** Opening any client tells the whole story top-to-bottom in one scroll; averages appear once ≥5 clients have closed.

### 1.6 Next-step discipline (pipeline hygiene)
- **Goal:** No lead dies of silence. (This is the cheapest ROI lever a sales org has.)
- **Scope:**
  - Every non-Completed/Lost client should have a next step with a date; dashboard flags clients with none or with overdue steps ("3 clients need a next step").
  - "Stale lead" indicator: no activity in N days (configurable, default 14) — amber at N, red at 2N.
  - Supervisor view: stale/no-next-step counts per rep.
- **Acceptance:** Rep home shows their follow-up debt; supervisor sees whose pipeline is going cold.

---

## Phase 2 — Time & Payroll (⏸️ maintain, don't invest)

> **Deprioritized (Jai, 2026-07-17):** clock-in stays functional but is not a focus and may be removed later. Build **nothing new** on top of time tracking. The two items below survive only because payroll must stay *correct* while the feature exists; do them late, or skip if time tracking is removed first.

### 2.1 Payroll export + period lock (keep — correctness)
- **Scope:** Per-pay-period CSV export with rates and totals; lock a pay period after export (edits require unlock + audit note).
- **Acceptance:** One click produces the file used to run payroll; locked periods can't silently change.

### 2.2 CA overtime flags (keep — small)
- **Scope:** Daily OT (>8h/>12h) computed on existing entries and shown in payroll views. Calculation help, not legal advice; verify current CA rules at build time.
- **Acceptance:** Pay-period summaries split regular/OT hours.

### ❌ Cut from this phase
- ~~Scheduling & shift planning~~ — investing in the feature we may remove.
- ~~Geolocation clock-in~~ — same reason.

---

## Phase 3 — Reporting & Intelligence

### 3.1 Weekly scoreboard — **promoted: this is the top of the hub (0.2 §1)**
- **Goal:** The thing everyone reads Monday morning. Not a separate page — the first section of the one-page hub.
- **Scope:** Week-over-week: new leads by source, pipeline movement, deals closed + revenue, follow-up debt (hours worked included small, while time tracking exists). Plain-language sentences over jargon ("You added 9 leads; 6 came from referrals."). Optional weekly email digest of the same content later.
- **Acceptance:** The Monday meeting runs off the top of the hub alone.

### 3.2 Rep performance view (fair, not gotcha)
- **Goal:** Coaching data, not surveillance.
- **Scope:** Per rep: hours, activities logged, clients touched, next-step compliance, close rate, revenue attributed to their assigned clients. Trends over time; visible to that rep too (same numbers, no secrets).
- **Acceptance:** A supervisor can prep a 1:1 from this page; the rep sees the same page about themselves.

### 3.3 Simple forecasting
- **Goal:** The useful sliver of Hyros forecasting, no AI needed.
- **Scope:** Pipeline-weighted projection: sum of (opportunity value × stage close-rate) from historical close rates per stage; monthly revenue projection alongside actuals on the scoreboard.
- **Acceptance:** "Projected revenue this quarter: $X" with a visible explanation of the math.

---

## Phase 4 — Platform & Polish

### 4.1 Notifications
- In-app first (bell + badge): overdue next steps, stale leads, correction-note replies, pay-period close reminders. Email later.

### 4.2 Audit trail
- Who changed what, when — time entries, rates, client reassignment, status changes. Supervisor-visible log per record. (Also the foundation multi-tenant will need.)

### 4.3 PWA / installable mobile
- Manifest + service worker so reps "install" it from the browser; offline clock-in queued and synced when back online. Big usability win for field crews; no app store needed.

### 4.4 Search
- Global search (clients, activities, entries) from the nav — supervisors live in this once data grows.

### 4.5 Multi-company groundwork (deliberate, later)
- **Decision made:** not building multi-tenant now. Cheap hedges while building everything above: never hardcode company name in logic (config value), keep all queries going through helper scopes, keep uploads namespaced by prefix. When it's time: `Company` model, scope every table to it, org signup + billing. Parked.

---

## Suggested build order

| Order | Item | Why first |
|---|---|---|
| 1 | 0.1 Design system + 0.2 one-page hub | The hub restructure IS the app now; do it before rolling Commit #2's card pattern to more pages (avoid restyling twice) |
| 2 | 1.1 Lead source | Smallest schema change with the biggest unlock; start collecting data NOW — every week without it is lost attribution history |
| 3 | 1.2 Spend + 1.3 Revenue | Two small forms; makes 1.4 possible |
| 4 | 3.1 Weekly scoreboard (hub top section) | The heart of the app per the new usage model — the Monday read |
| 5 | 1.6 Next-step discipline (hub "Needs Attention") | Cheap, immediate sales impact; feeds the hub |
| 6 | 1.4 ROI report | The money page under Reports |
| 7 | 1.5 Journey timeline | Uses existing data, big perceived value |
| 8 | 3.2 Rep view → 3.3 forecast | Reporting depth |
| 9 | 2.1 Payroll lock/export + 2.2 OT flags | Late — only while time tracking still exists |
| 10 | Phase 4 items as breathers between big features | |

---

## What we're NOT building (so nobody wastes a week on it)

- Anonymous website-visitor tracking / pixels (Hyros territory; needs the marketing site, not this app)
- Ad-platform API integrations pulling spend automatically (manual monthly entry is 2 min; revisit if channels multiply)
- Multi-touch attribution models (first-touch via lead source is right for this sales motion)
- AI chat/insights layer (the reports should be clear enough not to need one)
- Native iOS/Android apps (PWA covers it)
- Any new investment in clock-in/time tracking (scheduling, geolocation, live-timer polish) — the feature is on probation and may be removed
