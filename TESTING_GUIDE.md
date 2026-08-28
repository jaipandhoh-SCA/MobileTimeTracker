

# All Inclusive ADU Portal — Feature Guide & Testing Walkthrough

This guide walks through every feature in the app, explains how to use it, and
gives you sample data so you can test each one end-to-end.

---

## 1. Getting In (Login)

**How it works:** The landing page at `/` shows a "Sign in with Google" button
and a "Sign In (Dev)" button. The dev button creates or reuses a supervisor
account and logs you in immediately — no Google OAuth needed.

**Test it:**
1. Go to your app URL (e.g. `https://mobiletimetracker.onrender.com/`)
2. Click "Sign In (Dev)"
3. You should land on the Home dashboard

---

## 2. Home Dashboard

**Where:** `/home` (after login)

**What it shows:**
- **All users**: Pipeline summary, lead counts by status, recent clients,
  stale leads needing attention, channel performance cards, weekly brief.
- **All users**: "My Assignments" section — today's tasks and this week's tasks
  (from the scheduling system).
- **Supervisors**: "Portfolio Financials" collapsible section — contract value,
  budget vs actual, gross margin, AR outstanding, WIP mini-table (top 5 projects
  with progress bars), AR aging buckets, CSV/PDF export buttons.

**Test it:** Once you add a few clients and accept an estimate (sections below),
come back here to see both the pipeline and financial sections populate.

---

## 3. Client CRM

### 3a. Create a Client

**Where:** Clients tab → "New Client" button, or `/clients/new`

**Test data — create these 3 clients:**

| Name | Address | Phone | Email | Status |
|------|---------|-------|-------|--------|
| Maria Garcia | 1234 Oak Ave, Los Angeles CA 90001 | 310-555-0101 | maria@example.com | Lead |
| James Wilson | 5678 Pine St, Pasadena CA 91101 | 626-555-0202 | james@example.com | Prospect |
| Sarah Chen | 9012 Maple Dr, Glendale CA 91201 | 818-555-0303 | sarah@example.com | Active |

For each client, fill in:
- **Name, Address, Phone, Email** — from the table
- **Status** — set from the dropdown
- **ADU details** (optional but good for testing): Type of ADU = "Detached",
  Desired SF = "600", Bedrooms = "1", Bathrooms = "1"
- **Opportunity Value** — enter $150,000

### 3b. Client Detail Page

**Where:** Click any client name → `/clients/<id>/edit`

**What you can do:**
- Edit all fields (click "Edit Mode" toggle)
- Change status via the dropdown (auto-saves)
- Add activities/notes in the timeline
- Upload property images via the "Property Files" section
- See Estimates, Documents & Permits quick-access cards

**Test it:** Open Maria Garcia, toggle to Edit Mode, change a field, save.

### 3c. Client Statuses

The pipeline: **Lead → Prospect → Active → Completed** (also On Hold, Lost)

- Changing to "Active" auto-carries any accepted estimate into the project
- Changing to "Completed" prompts for final contract value

---

## 4. Lead Sources & Channel Spend

### 4a. Lead Sources

**Where:** Profile menu → Lead Sources, or `/settings/lead-sources`

**Test data — create these sources:**

| Name | Channel Type |
|------|-------------|
| Instagram Organic | organic_social |
| Meta Ads | paid_ads |
| Referral | referral |
| Phone Call | phone |
| Website | website |

### 4b. Channel Spend

**Where:** Channel Spend tab in the nav, or `/channel-spend`

**What it does:** Track monthly ad/marketing spend per lead source. The home
dashboard uses this to calculate channel ROI.

**Test it:**
1. Go to Channel Spend
2. Add a spend entry: Source = "Meta Ads", Amount = $2,500, Month = current month
3. Go back to Home — the Meta Ads channel card should show the spend

---

## 5. Cost Codes

**Where:** Profile menu → Cost Codes, or `/settings/cost-codes`

**What they are:** Hierarchical construction cost categories (01 through 17)
used for budgeting, time tracking, and job costing.

**First-time setup:** The cost codes are seeded automatically by the migration.
If they're missing, you'll need to run the seed script. Check if they exist by
visiting the Cost Codes settings page.

**Test it:** Go to Cost Codes — you should see codes like:
- 01 Site Work
- 02 Foundation
- 03 Framing
- ...through 17 Landscaping

If the list is empty, the migration seed didn't run. See the "Seeding Data"
section at the bottom.

---

## 6. Assembly Items (Cost Database)

**Where:** Cost Codes settings → "Assembly Items" button, or `/settings/assembly-items`

**What they are:** A reusable database of construction items with unit costs,
labor/material split, and waste percentages. These feed into estimates.

**Test it:** You should see ~55 pre-seeded items (e.g. "Concrete Footing",
"2x6 Wall Framing", "Standing Seam Roofing"). If empty, see "Seeding Data" below.

---

## 7. Estimating

### 7a. Create an Estimate

**Where:** Estimates tab → "New Estimate", or from a client page → Estimates card

**Test it step by step:**

1. Go to Estimates → New Estimate
2. Select **Client** = Maria Garcia
3. Select **Template** = "Detached ADU" (pre-loads line items)
4. Enter **Name** = "Maria Garcia - 600SF Detached"
5. Set **SF** = 600, **ADU Type** = Detached
6. Click **Create Estimate**

### 7b. Edit an Estimate

**Where:** The estimate editor page after creation

**What you can do:**
- Edit line items inline (qty, unit cost, waste%)
- Add/remove line items
- Adjust markup (%), overhead (%), contingency (%)
- Toggle between Internal View (shows all costs) and Client View (hides markup)

**Test it:**
1. On the estimate you just created, change a line item qty (e.g. set Framing to 650 SF)
2. Adjust Markup to 15%, Overhead to 8%, Contingency to 5%
3. Check the summary — it should show Direct Cost, Overhead, Markup, Contingency, Total
4. Click "Client View" — should hide internal cost breakdowns

### 7c. Accept an Estimate

**Where:** Estimate view → "Accept → Budget" button

**What it does:** Creates Budget lines by cost code on the client's default
project and sets the contract value.

**Test it:**
1. Open the estimate → click "Accept → Budget"
2. Confirm the dialog
3. Go to the client page — the contract value should be set
4. The estimate status should show "Accepted"

### 7d. Duplicate an Estimate

Click "Duplicate" on any estimate to clone it. Useful for creating variations.

---

## 8. Proposals

### 8a. Create a Proposal

**Where:** Estimate view → "Create Proposal" button

**What it does:** Generates a branded, client-facing proposal from the estimate.
Hides internal markup/costs — the client only sees the total per line item.

**Test it:**
1. Open Maria Garcia's accepted estimate
2. Click "Create Proposal →"
3. Fill in:
   - **Cover Note** = "Thank you for considering All Inclusive ADU for your project."
   - **Scope of Work** = "Complete construction of a 600 SF detached ADU including all permits, engineering, and finishes."
   - **Exclusions** = "Furniture, appliances, landscaping beyond 5ft from structure."
   - **Validity Days** = 30
4. Click "Create Proposal"

### 8b. Send a Proposal

**Where:** Proposal view → "Mark Sent & Get Link"

**Test it:**
1. On the proposal view, click "Mark Sent & Get Link"
2. Copy the share URL that appears
3. Open that URL in an incognito window — you'll see the client-facing proposal
4. The client can enter their name and click "Accept Proposal"

### 8c. Accept a Proposal (as the client)

**Test it:**
1. Open the public proposal link in incognito
2. Enter name = "Maria Garcia"
3. Click "Accept Proposal"
4. Back in the app, the proposal should show "Accepted by Maria Garcia"

---

## 9. Contracts

### 9a. Create a Contract

**Where:** Accepted proposal view → "Create Contract →" button

**Test it:**
1. Open the accepted proposal for Maria Garcia
2. Click "Create Contract →"
3. Fill in:
   - **Contract Number** = "AIA-2026-001"
   - **Scope of Work** — auto-filled from proposal
   - **Terms** — auto-filled with default terms
   - **Draw Schedule** — pre-filled with 5 milestones:
     - Deposit (10%), Foundation (20%), Framing (25%), Rough-In (25%), Completion (20%)
   - Make sure the percentages add up to 100%
4. Click "Create Contract"

### 9b. Send a Contract

**Where:** Contract view → "Send & Get Link"

**Test it:**
1. Click "Send & Get Link" on the contract view
2. Copy the share URL
3. Open in incognito — you'll see the contract with scope, payment schedule, and terms

### 9c. Sign a Contract (E-Signature)

**Where:** Public contract page → signature form at the bottom

**Test it:**
1. Open the public contract link in incognito
2. Enter **Name** = "Maria Garcia"
3. Enter **Email** = "maria@example.com"
4. Draw a signature on the canvas pad
5. Click "Sign Contract"
6. Back in the app, the contract should show:
   - Status = "Signed"
   - Signature image displayed
   - Signed by name, date, IP address
   - Audit log stored in R2

---

## 10. Document Management

### 10a. Upload Documents

**Where:** Client page → "Documents & Permits" card → "Manage", or
`/clients/<id>/documents`

**Test it — upload these files (use any PDFs/images you have):**

| Title | Folder | File |
|-------|--------|------|
| Site Survey | Plans | any-pdf.pdf |
| Foundation Plan | Plans | any-pdf.pdf |
| Building Permit App | Permits | any-pdf.pdf |
| Structural Calcs | Specs | any-pdf.pdf |
| Site Photo 1 | Photos | any-image.jpg |

1. Click "Upload Document"
2. Select Folder = "Plans"
3. Enter Title = "Site Survey"
4. Choose a PDF file
5. Click Upload
6. Repeat for each file above

### 10b. Version a Drawing (Critical Feature)

**Where:** Document detail page → "Upload New Revision"

**Test it:**
1. Click on "Foundation Plan" in the Plans folder
2. Click "Upload New Revision"
3. Choose a different PDF file
4. Enter Change Note = "Updated per structural engineer review"
5. Click "Upload Revision"
6. You should see:
   - Version History showing v1 and v2
   - v2 marked as "Current"
   - v1 still downloadable
7. Upload another revision (v3) — all 3 versions should be listed

### 10c. Supersede a Drawing

**Where:** Document detail → "Mark Superseded" (only for Plans folder)

**Test it:**
1. Go to "Site Survey" document
2. Click "Mark Superseded"
3. Optionally select "Foundation Plan" as the replacement
4. Confirm — the Site Survey should show a "Superseded" badge
5. Back on the documents list, Site Survey should no longer appear (it's filtered out)

### 10d. PDF Viewer + Markup

**Where:** Any PDF document → "View" or "View PDF" button

**Test it:**
1. Open any PDF document
2. Click "View PDF" (or the "View" link on the documents list)
3. Try the markup tools:
   - **Pen** — draw in red on the PDF
   - **Highlight** — yellow semi-transparent highlight
   - **Text** — click anywhere to add a text annotation
   - **Pan** — back to normal scroll mode
4. Click "Save PNG" — downloads the current page with your markup as an image
5. Click "Clear" to erase markup
6. Use Prev/Next to navigate pages, +/- to zoom

### 10e. Edit Document Details

**Where:** Document detail → "Edit Details" button

Change title, folder, visibility (Team vs Supervisor Only), description.

### 10f. Document Visibility

- **Team** = everyone can see it
- **Supervisor only** = hidden from reps (shown with a purple badge)

---

## 11. Permit Tracking

### 11a. Create a Permit

**Where:** Documents page → "New Permit", or `/clients/<id>/permits/new`

**Test data — create these permits for Maria Garcia:**

| Type | Jurisdiction | Status | Submitted | Fee |
|------|-------------|--------|-----------|-----|
| Building Permit | City of Los Angeles | Submitted | 2026-07-15 | $4,500 |
| Grading Permit | City of Los Angeles | Approved | 2026-06-01 | $800 |
| School Fee | LAUSD | Not Started | | $3,200 |

**Test it:**
1. Click "New Permit"
2. Fill in Type = "Building Permit", Jurisdiction = "City of Los Angeles"
3. Set Status = "Submitted", Submitted Date = 2026-07-15
4. Enter Fee = $4,500, leave Fee Paid unchecked
5. Save
6. Repeat for the other two permits

### 11b. Track Permit Status Changes

**Where:** Edit any permit → change the Status dropdown

**Test it:**
1. Edit the Building Permit
2. Change Status from "Submitted" to "Corrections Required"
3. Set Corrections Due = a date in the past (e.g. 2026-08-01)
4. Enter Corrections Note = "Revise setback calculations per plan check"
5. Save
6. Back on the permits tab — it should show "OVERDUE" in red

### 11c. Overdue Detection

Permits show as overdue when:
- Status = "Corrections Required" and corrections_due_date is past
- Status = "Issued" and expiration_date is past

### 11d. Days in Review

The "Days" column shows how many days since submission for permits in
"Submitted" or "In Review" status.

---

## 12. Time Tracking (On Probation)

**Where:** My Logs tab, or `/my-logs`

**What it does:** Clock in/out, manual time entries, approval workflow.

**Note:** Time tracking is on probation — it works but we're not building new
features on it.

**Test it:**
1. Go to My Logs
2. Click "Quick Log" to create a manual time entry:
   - Client = Maria Garcia
   - Date = today
   - Hours = 2.5
   - Description = "Site visit and measurements"
3. As a supervisor, go to Admin → Payroll to see the entry and approve it

---

## 13. Admin Dashboard

**Where:** Profile menu → Admin, or `/admin` (supervisor only)

**What it shows:** Payroll summary, time entry approvals, job costing
reconciliation, team hours by cost code.

**Test it:** After creating a few time entries, visit the Admin dashboard to see
the payroll and job costing data.

---

## 14. User Management

**Where:** Profile menu → Manage Users, or `/admin/users` (supervisor only)

**What you can do:**
- See all users
- Set hourly rates and burden multipliers (for job costing)
- Add authorized emails (people allowed to sign up via Google OAuth)
- Change roles (supervisor/rep)

---

## 15. UI Styleguide

**Where:** `/styleguide` (supervisor only)

Shows all 15 UI macros (buttons, inputs, cards, etc.) rendered with examples.
Useful for design consistency.

---

## 16. Project Scheduling

### 16a. Create Schedule Phases

**Where:** Client page → default project → "Schedule" button, or
`/schedule/<project_id>`

**Test it:**
1. Open Maria Garcia's project schedule
2. Click "Add Phase"
3. Create these phases in order:
   - Foundation (color: #ef4444)
   - Framing (color: #f59e0b)
   - Rough-In (color: #3b82f6)
   - Finishes (color: #10b981)

### 16b. Create Tasks

**Where:** Schedule view → "Add Task" button

**Test data — create these tasks:**

| Task Name | Phase | Start | End | Priority | Status |
|-----------|-------|-------|-----|----------|--------|
| Excavation | Foundation | today | today+3 | High | In Progress |
| Pour footings | Foundation | today+4 | today+6 | High | Not Started |
| Frame walls | Framing | today+7 | today+12 | Medium | Not Started |
| Rough plumbing | Rough-In | today+13 | today+15 | Medium | Not Started |

### 16c. My Tasks (Mobile View)

**Where:** Tasks tab in nav, or `/my-tasks`

Shows tasks assigned to the current user, grouped by "Today", "This Week",
and "Overdue". Designed for field crews on mobile.

### 16d. Gantt Chart

**Where:** Schedule view → Gantt tab

Canvas-based Gantt chart showing phases and tasks on a timeline. No external
library needed — rendered with vanilla JS and HTML5 Canvas.

---

## 17. Daily Field Logs

### 17a. Create a Daily Log

**Where:** Logs tab in nav → "New Log", or `/daily-logs/new`

**Test data:**
1. Click "New Log"
2. Set Client = Maria Garcia, Date = today
3. Fill in:
   - Crew Count = 4
   - Crew Names = "Mike, Juan, Alex, Dev"
   - Hours Regular = 8, Hours OT = 0
   - Work Completed = "Completed excavation and form setup for foundation"
   - Weather = auto-fetched (or enter manually: Clear, 85°F)
4. Save as Draft or Final

### 17b. Add Photos to a Log

**Where:** Daily log edit page → "Add Photos" section

Upload construction photos. On mobile, the camera capture button opens the
device camera directly. Photos are stored in R2 under `daily-logs/`.

### 17c. Daily Log PDF

**Where:** Daily log view → "Download PDF" button

Generates a PDF of the day's log using fpdf2. Also available as a weekly
summary PDF.

### 17d. Offline Daily Logs

Daily logs support offline entry via the sync queue. If you create a log while
offline, it's stored in localStorage and synced when connectivity returns.

---

## 18. Change Orders

### 18a. Create a Change Order

**Where:** COs tab in nav → "New CO", or `/change-orders/new`

**Test data:**
1. Click "New CO"
2. Select Client = Maria Garcia
3. Fill in:
   - CO Number = CO-001
   - Title = "Add skylight to bedroom"
   - Description = "Client requests 2x3 skylight in master bedroom"
   - Price to Client = $3,500
4. Add line items:
   - "Skylight unit" — Cost Code: 16 Windows & Doors, Amount: $1,200
   - "Install labor" — Cost Code: 16 Windows & Doors, Amount: $800
   - "Flashing/waterproofing" — Cost Code: 04 Roofing, Amount: $500
5. Save

### 18b. Approve a Change Order

**Where:** CO view → "Approve" button, or via the client portal (e-signature)

Approving a CO:
- Adds the price_to_client to the project contract value
- Creates budget lines from the CO items
- Logs a ClientActivity entry
- Can be signed by the client via a public share link with e-signature

---

## 19. Billing & Invoicing

### 19a. Create an Invoice

**Where:** Client billing hub (from contract view) → "New Invoice"

**Prerequisites:** Must have a signed contract with draw schedule items.

**Test it:**
1. Open Maria Garcia's contract → click "Billing"
2. Click "New Invoice"
3. Select draw schedule milestones to bill (e.g., Deposit at 10%)
4. Add any approved, unbilled change orders
5. Set due date = 30 days from today
6. Create the invoice

### 19b. Record a Payment

**Where:** Invoice view → "Record Payment"

**Test it:**
1. Open the invoice
2. Click "Record Payment"
3. Enter Amount = $25,000, Method = Check, Reference = "Check #1234"
4. Save — invoice should show "Partial" status
5. Record another payment for the remaining balance — should show "Paid"

### 19c. Void an Invoice

**Where:** Invoice view → "Void" button

Voiding un-bills any associated change orders so they can be re-billed.
Creates an audit trail entry (ClientActivity).

### 19d. Public Invoice + Stripe

Invoices have a public share link. If Stripe is configured, clients can pay
online via a Stripe Checkout session.

---

## 20. Financial Reports

### 20a. Portfolio Financials Page

**Where:** Reports → Financials, or `/reports/financials`

**What it shows:**
- 7 summary cards: Active Projects, Contract Value, Total Budget, Actual Costs,
  Committed, Cost to Complete, Gross Margin (with %)
- WIP table: every active project with contract value, budget, actual, committed,
  CTC, progress bar, and health badge (On Track / Watch / Over Budget)
- AR Aging: total outstanding, 5 aging buckets (Current / 1-30 / 31-60 / 61-90 / 90+),
  and a detail table of every outstanding invoice

**Test it:**
1. After accepting an estimate and creating some cost entries, visit `/reports/financials`
2. You should see the project in the WIP table
3. After creating and sending an invoice, the AR section should populate

### 20b. Export

**Where:** Financials page → "Export CSV" or "Export PDF"

CSV downloads a spreadsheet; PDF generates a formatted report via fpdf2.

---

## 21. Client Portal

### 21a. Create a Client User

**Where:** Client detail page → "Portal" section (supervisor only)

**Test it:**
1. Open Maria Garcia's client page
2. In the Portal section, enter email = "maria@example.com", name = "Maria Garcia"
3. Click "Create Portal User"
4. A magic link is generated — in dev mode, it's shown as a flash message

### 21b. Magic Link Login

**Where:** `/portal/login`

Clients enter their email, receive a magic link, and click it to log in.
Links are single-use and expire after 30 minutes. No password needed.

### 21c. Portal Dashboard

**Where:** `/portal/` (after client login)

Shows the client:
- Project progress (phases and task completion)
- Draw schedule / payment milestones
- Recent construction photos
- Unread messages count
- Pending selections count

### 21d. Portal Messages

**Where:** `/portal/messages`

Two-way message thread between client and staff. Staff messages are marked
as read when the client views them. Client messages notify supervisors
(respecting notification preferences).

### 21e. Portal Selections

**Where:** `/portal/selections`

Clients choose finish/fixture options (flooring, countertops, etc.) from
categories set up by staff. Each selection:
- Creates a ClientActivity entry
- Notifies supervisors (if their preferences allow)
- Can trigger a change order for price deltas

### 21f. Auth Isolation

The client portal is **fully isolated** from staff auth:
- ClientUser uses `session['client_user_id']` — never flask-login
- Staff uses flask-login (`current_user`) — never client sessions
- A client session CANNOT access any staff route (returns 302)
- A staff session CANNOT access portal routes
- Client A cannot see Client B's data

---

## 22. Notification Preferences

**Where:** Profile menu → Notifications, or `/settings/notifications`

**Preference categories:**
- **Task Notifications**: new task assigned, task updated, task reminders
- **Financial Notifications**: invoice created, payment received, estimate accepted
- **Client Portal Notifications**: portal message received, selection made

Unchecking a preference suppresses that notification type for your account.
In-app notifications still appear in the bell dropdown; email/SMS delivery
is a future feature.

---

## 23. PWA / Mobile Install

### 23a. Install on iOS

1. Open the app in Safari
2. Tap the Share button → "Add to Home Screen"
3. The app launches in standalone mode (no browser chrome)

### 23b. Install on Android

1. Open the app in Chrome
2. Tap the install banner (or Menu → "Install app")
3. The app appears as a standalone icon on the home screen

### 23c. Offline Support

When offline:
- Previously visited pages load from the service worker cache
- An amber "You are offline" banner appears at the top
- POST/PUT actions (time entries, daily logs) are queued in IndexedDB
- When connectivity returns, queued actions replay automatically via Background Sync

---

## 24. Automated Test Suites

Run these from the project root to verify core logic without needing a live database:

```bash
# Access-control tests (11 tests)
.venv/bin/python -m unittest test_access_control -v

# Cost math tests (20 tests)
.venv/bin/python -m unittest test_cost_math -v

# Portal isolation tests (8 tests)
.venv/bin/python -m unittest test_portal_isolation -v

# All tests at once
.venv/bin/python -m unittest test_access_control test_cost_math test_portal_isolation -v
```

**What they cover:**
- `test_access_control.py` — rep vs supervisor roles, unauthenticated redirects,
  client portal isolation, session tampering, magic link security
- `test_cost_math.py` — budget/actual/committed aggregation, CostEntry upsert
  idempotency, estimate math (waste, markup, overhead, contingency), invoice
  recalculate (retainage, partial/full payment), change order totals
- `test_portal_isolation.py` — client session can't access staff routes, cross-client
  data isolation, inactive client blocked, magic link single-use

All tests use SQLite in-memory — no external database or API keys needed.

---

## Seeding Data (If Tables Are Empty)

If cost codes and assembly items are empty after deploy (because `db.create_all()`
created tables before the migration seeds ran), you need to seed manually.

**Option A — Run via Render Shell:**

Go to Render → your service → Shell tab, then run:

```bash
uv run python3 -c "
from app import app, db
from models import CostCode, AssemblyItem, EstimateTemplate, EstimateTemplateItem
from decimal import Decimal

with app.app_context():
    # Check if already seeded
    if CostCode.query.count() > 0:
        print(f'Already have {CostCode.query.count()} cost codes')
    else:
        # Seed cost codes
        codes = [
            ('01', 'Site Work'), ('02', 'Foundation'), ('03', 'Framing'),
            ('04', 'Roofing'), ('05', 'Exterior'), ('06', 'Plumbing'),
            ('07', 'Electrical'), ('08', 'HVAC'), ('09', 'Insulation'),
            ('10', 'Drywall'), ('11', 'Interior Finishes'), ('12', 'Flooring'),
            ('13', 'Painting'), ('14', 'Cabinets & Countertops'),
            ('15', 'Appliances & Fixtures'), ('16', 'Windows & Doors'),
            ('17', 'Landscaping'),
        ]
        for code, name in codes:
            cc = CostCode(code=code, name=name, default_cost_type='Labor')
            db.session.add(cc)
        db.session.commit()
        print(f'Seeded {len(codes)} cost codes')

    if AssemblyItem.query.count() > 0:
        print(f'Already have {AssemblyItem.query.count()} assembly items')
    else:
        print('Assembly items need the full migration seed - run: alembic upgrade head')
        print('Or stamp current: alembic stamp d5a7b1c63e28')
"
```

**Option B — Stamp Alembic and re-run:**

```bash
uv run alembic stamp d5a7b1c63e28
```

This tells Alembic the DB is at the latest migration. If tables exist but are
empty, you'll still need to seed via Option A or by running the full migration
upgrade on a fresh database.

---

## Quick Smoke Test Checklist

After deploy, run through this checklist to verify everything works:

- [ ] Landing page loads at `/`
- [ ] Dev login works (if ALLOW_DEV_LOGIN=true)
- [ ] Home dashboard loads after login
- [ ] Create a client (Maria Garcia from test data above)
- [ ] Client detail page loads, edit mode works
- [ ] Cost codes page shows 17 codes
- [ ] Create an estimate from a template
- [ ] Edit estimate line items
- [ ] Accept estimate → budget created
- [ ] Create proposal from estimate
- [ ] Send proposal → copy public link → opens in incognito
- [ ] Accept proposal from public page
- [ ] Create contract from accepted proposal
- [ ] Send contract → sign from public page with signature pad
- [ ] Upload a document to Plans folder
- [ ] Upload a revision → version history shows v1 and v2
- [ ] Open a PDF in the viewer → use pen/highlight tools
- [ ] Create a permit → change status → check overdue detection
- [ ] Log a time entry from My Logs
- [ ] Admin dashboard loads with data
