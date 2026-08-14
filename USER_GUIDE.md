# All Inclusive ADU Portal — User Guide

A web app built for the All Inclusive ADU sales and construction team. It combines a **CRM** (client/lead management), **estimating**, **scheduling**, **daily field logs**, **change orders**, **billing/invoicing**, **time tracking with payroll**, **job costing**, **reporting**, a **client portal**, and **integrations** — all in one place, optimized for mobile.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [The Hub (Home Dashboard)](#the-hub)
3. [Clients & CRM](#clients--crm)
4. [Estimating](#estimating)
5. [Proposals & Contracts](#proposals--contracts)
6. [Scheduling](#scheduling)
7. [Daily Field Logs](#daily-field-logs)
8. [Change Orders](#change-orders)
9. [Billing & Invoicing](#billing--invoicing)
10. [Time Tracking](#time-tracking)
11. [My Time Logs](#my-time-logs)
12. [Payroll Dashboard (Supervisors)](#payroll-dashboard)
13. [Job Costing](#job-costing)
14. [Reports](#reports)
15. [Client Portal](#client-portal)
16. [Notification Preferences](#notification-preferences)
17. [Settings & Administration](#settings--administration)
18. [Roles & Permissions](#roles--permissions)
19. [PWA / Mobile Install](#pwa--mobile-install)
20. [Key Concepts](#key-concepts)

---

## Getting Started

### Logging In

**Dev / Staging**: Click the **"Sign In (Dev)"** button on the landing page. This creates or reuses a supervisor account and logs you in immediately — no Google setup required.

**Production (when configured)**: Sign in with your company Google account. The app uses Google login — no separate password needed.

- **First-time users**: A supervisor must add your Google email to the authorized users list before you can log in. Once added, just click "Sign in with Google."
- **Switching accounts**: Use "Fresh Login" from the profile menu to sign in with a different Google account.

### Navigation

The top bar has links to every section:

| Link | What It Does |
|------|-------------|
| **Hub** | Your home dashboard — weekly snapshot, assignments, and financials |
| **Time** | Clock in/out and log hours |
| **Clients** | View and manage your client list |
| **Estimates** | Create and manage project estimates |
| **Tasks** | Your assigned schedule tasks (My Tasks) |
| **Logs** | Daily field logs |
| **Change Orders** | Track change orders across projects |
| **Reports** | Channel spend, ROI, and financial reports (supervisors only) |
| **Settings** | User management, cost codes, integrations (supervisors only) |

On mobile, tap the menu icon (three lines) to see these links.

There's also a **search bar** at the top — type a client name to jump straight to their record. A **notification bell** shows unread alerts (task assignments, financial events, portal messages).

---

## The Hub

Your home dashboard. It shows a weekly snapshot — not a daily tool. Check it at the start of the week to know where you stand.

### What You See (Reps)

- **Your clients** broken down by status: Leads, Prospects, Active, Completed, On Hold — with total opportunity values
- **Recent clients** — the 5 most recently created
- **Upcoming follow-ups** — next steps you've scheduled on client activities
- **Recent activity** — your latest logged calls, meetings, notes
- **Weekly performance** — new leads, value added, conversations, and meetings this week vs. last week
- **My Assignments** — schedule tasks assigned to you (today, this week, overdue)

### What You See (Supervisors)

Everything above, plus:

- **Filter by rep** — dropdown to view any rep's dashboard, or the whole company
- **Portfolio financials** — total contract value, budget used, and cost summary across active projects
- **Integration status** — whether GHL and Meta Ads are connected and last sync time
- **Lead source backfill banner** — if any clients are missing their lead source, you'll see a prompt to fix them (needed for accurate ROI reports)

---

## Clients & CRM

### Viewing Clients

Go to **Clients** to see your client list.

- **Reps** see only their assigned clients
- **Supervisors** see all clients, with a toggle to show inactive ones

The list shows status, opportunity value, contact info, and who created the lead. Click any row to open the client's full record.

### Creating a Client

Click **+ New Client**. Fill in:

- **Name and address** (required)
- **Contact info** — name, phone, email
- **Lead source** — where this lead came from (Google Ads, referral, etc.)
- **ADU project details** — type of ADU, square footage, zoning, beds/baths, style, features
- **Financial info** — budget, property values, expected ROI, financing
- **Timeline** — estimated start/end dates, permitting status
- **Status** — Lead, Prospect, Active, Completed, or On Hold
- **Opportunity value** — estimated deal size

### The Client Record

Open any client to see their full history and manage the deal:

**Timeline** — A complete chronological record of everything that's happened:
- When the lead was created and by whom
- Every status change (Lead -> Prospect -> Active, etc.)
- All logged activities (calls, meetings, notes, site visits)
- Estimate accepted, invoice created/voided, change orders — all appear as audit entries
- Upcoming next steps

**Activities** — Log what you've done:
- Choose a type: Call, Email, Meeting, Site Visit, Proposal, or Note
- Add your notes (what happened, what was discussed)
- Set a next step with a date (e.g., "Follow up on permit status" on 08/15)
- Attach a file if needed (proposals, photos, documents)

**Property Images** — Upload and view photos of the property. Drag and drop or use the file picker. Supports JPG, PNG, GIF, and WebP up to 5 MB each.

**Quick Actions** (top of the page):
- Change status with one click
- Update the opportunity value or final contract value
- Supervisors can reassign the client to a different rep

### Projects

Each client can have **multiple ADU projects**. A default project is created automatically when a client is added. Each project tracks its own:

- Contract value
- Budget lines (by cost code)
- Cost entries (labor, material, etc.)
- Schedule phases and tasks
- Daily logs

The client's **total contract value** is the sum of all project contract values.

---

## Estimating

Create detailed cost estimates for ADU projects.

### Creating an Estimate

Go to **Estimates -> + New Estimate**.

1. **Select a client** (required)
2. **Choose a template** — pre-built templates for common ADU types:
   - Studio ADU
   - 1-Bedroom ADU
   - 2-Bedroom ADU
   - Detached ADU
   - Garage Conversion
3. Templates pre-load typical line items with quantities and unit costs. You can also start blank.
4. **Edit line items** — adjust quantities, unit costs, labor/material splits, and waste percentages
5. **Set markups** — overhead %, markup %, and contingency % are applied on top of the base cost

### Estimate Math

Each line item calculates:
- **Extended cost** = Qty x Unit Cost x (1 + Waste%)
- **Labor portion** = Extended Cost x Labor%
- **Material portion** = Extended Cost x Material%

The estimate totals:
- **Subtotal** = sum of all line items
- **+ Overhead** = Subtotal x Overhead%
- **+ Markup** = Subtotal x Markup%
- **+ Contingency** = Subtotal x Contingency%
- **= Total** (this becomes the contract value when accepted)

### Estimate Status

| Status | Meaning |
|--------|---------|
| **Draft** | Still being edited |
| **Sent** | Shared with the client |
| **Accepted** | Client approved — budget lines are created, contract value is set |
| **Rejected** | Client declined |
| **Expired** | Past expiration date |

When an estimate is **accepted**:
- Budget lines are created for each cost code in the estimate
- The project's contract value is set to the estimate total
- An audit trail entry is logged on the client timeline

### Assembly Items

The system includes 55+ pre-loaded assembly items (concrete, framing, roofing, electrical, plumbing, etc.) with unit costs, labor/material splits, and waste factors. These are linked to cost codes so estimates automatically feed into job costing.

---

## Proposals & Contracts

Create professional proposals and contracts from accepted estimates.

- **Proposals** — Customer-facing documents generated from estimates with your branding
- **Contracts** — Formal agreements linked to a client and project with scope, payment terms, and signatures

Both are accessible from the client record.

---

## Scheduling

Manage project timelines with phases, tasks, and crew assignments.

### Views

- **Gantt Chart** — Canvas-based timeline view showing tasks on a horizontal timeline with dependencies
- **Calendar** — Monthly calendar view (Alpine.js powered) showing tasks by date
- **List View** — Sortable table of all tasks with status filters
- **My Tasks** — Mobile-optimized view of your assignments: today, this week, and overdue

### Phases

Group tasks into project phases (e.g., Foundation, Framing, MEP, Finish). Each phase has:
- A name and sort order
- A color for visual distinction on the Gantt chart

### Tasks

Each task has:
- **Name** and optional **description**
- **Start date** and **end date**
- **Status**: Not Started, In Progress, Complete, Blocked
- **Priority**: Low, Medium, High, Urgent
- **Phase** (optional) — which project phase it belongs to
- **Cost code** (optional) — links to job costing
- **Assignees** — staff users or subcontractor names
- **Dependencies** — other tasks that must finish first (Finish-to-Start)

### Notifications

When you're assigned to a task or a task changes, you'll receive an in-app notification (bell icon in the nav bar). Notification preferences can be configured in Settings.

---

## Daily Field Logs

Document daily construction progress with photos and weather data.

### Creating a Log

Go to **Logs -> + New Log**.

1. Select the **client** and **project**
2. The **date** defaults to today (one log per user per client per day)
3. Fill in:
   - **Crew members** present
   - **Hours** worked on site
   - **Work performed** — description of the day's activities
   - **Weather** — auto-fetched from the project address (Open-Meteo, no API key needed)
   - **Delays** — any issues that slowed work
4. **Attach photos** — with captions and optional cost code tags. Camera capture supported on mobile.
5. Save as **Draft** or finalize as **Final**

### Log Features

- **Weather auto-fetch** — Based on the project address, temperature and conditions are pulled automatically
- **Photos** — Stored in Cloudflare R2, with camera capture support on mobile devices
- **PDF export** — Generate a single-day PDF or weekly summary PDF for sharing
- **Shareable links** — HMAC-signed URLs for sharing PDFs without login
- **Offline support** — Logs can be saved offline and synced when back online (see PWA section)
- **Timeline integration** — Each finalized log creates an entry on the client activity timeline

---

## Change Orders

Track scope changes during construction with cost impact.

### Creating a Change Order

Go to **Change Orders -> + New Change Order**.

1. Select the **client** and **project**
2. Add a **title** and **description** of the change
3. Add **line items** — each with a description, cost code, quantity, unit cost, and labor/material split
4. The **total** is calculated from the line items
5. Set status: Draft, Pending, Approved, Rejected

### Impact

When a change order is **approved**:
- The project's contract value is adjusted (increased or decreased)
- Budget lines are updated for affected cost codes
- An audit trail entry is logged

---

## Billing & Invoicing

Create and manage invoices for construction projects.

### Creating an Invoice

From a client's record, create an invoice:

1. Select line items or enter amounts
2. Set **retainage** percentage (holdback for construction completion)
3. The invoice calculates: subtotal, retainage withheld, and total due

### Invoice Status

| Status | Meaning |
|--------|---------|
| **Draft** | Being prepared |
| **Sent** | Sent to client |
| **Partial** | Some payments received |
| **Paid** | Fully paid |
| **Voided** | Cancelled (audit trail logged) |

### Payments

Record payments against invoices:
- Payment amount, date, method, and reference number
- Partial payments are tracked — the invoice shows remaining balance
- Failed payments don't reduce the balance
- When total payments reach the amount due, status auto-updates to Paid

### Audit Trail

All financial actions are logged on the client timeline:
- Invoice created/voided with amounts
- Estimate accepted with contract value
- Change orders approved with cost impact

---

## Time Tracking

There are two ways to log time: the **clock** and **quick log**.

> Time tracking is currently in maintenance mode — it works, but no new features are being added to it.

### Clock In / Clock Out

1. From the Hub or Time page, tap **Clock In** to start your shift
2. While clocked in, you'll see your elapsed time
3. **Breaks**: After 1 hour, you can take a 15-minute break. After 2 hours, you can take a 30-minute lunch. These are deducted from your total automatically.
4. When done, tap **Clock Out**
5. You'll be asked to:
   - Select a **client** (or "Daily Activities" for non-client work)
   - Optionally select a **cost code** (for job costing)
   - Write a **description** of what you did (minimum 10 characters)
6. Your time entry is created with status **Pending** — a supervisor needs to approve it before it counts toward payroll

### Quick Log

Use this to manually log hours without the clock — for example, if you forgot to clock in, or you're logging time after the fact.

1. Go to **Time -> Quick Log**
2. Enter the **date**, **hours** (in 15-minute increments: 0.25, 0.50, 0.75, etc.), **client**, and **description**
3. Optionally select a **cost code**
4. Submit — the entry is created as **Pending**

### How Hours Are Rounded

All hours are rounded to the nearest **15 minutes** (0.25 hours). For example:
- 1 hour 10 minutes -> 1.00 hours
- 1 hour 15 minutes -> 1.25 hours
- 2 hours 37 minutes -> 2.50 hours

---

## My Time Logs

Go to **Time -> My Logs** to see all your time entries.

### What You See

- **Summary cards** — Approved hours, billable hours (time on clients), number of approved entries, and estimated pay for the period
- **Daily hours chart** — a bar chart of your hours by day
- **Entry table** — every entry with date, client, hours, status, description, and type (Clock or Manual)

### Status Badges

| Badge | Meaning |
|-------|---------|
| **Pending** (amber) | Submitted, waiting for supervisor approval |
| **Approved** (green) | Approved — counts toward your pay |
| **Rejected** (red) | Rejected by supervisor — check with them for the reason |

### Filtering

Use the filters to narrow down entries:
- **Period presets**: Current Pay Period, Previous Pay Period, Month to Date, Last 30 Days
- **Custom dates**: Pick a specific From and To date
- **Client**: Filter to entries for a specific client

---

## Payroll Dashboard

**Supervisors only.** Go to **/admin** to manage payroll and approve time.

### Summary Cards

At the top you'll see:
- **Approved Hours** — total approved hours in the current period
- **Billable** — approved hours on client work (not "Daily Activities")
- **Pending Hours** — hours still waiting for your approval
- **Total Entries** — all entries in the filtered view
- **Active Jobs** — number of unique clients with approved time

### Pending Approval Queue

A table of all pending time entries. For each entry you can see the date, rep, client, cost code, hours, and description.

**To approve or reject entries:**
- **Individual**: Click "Edit" to open the entry, then use the Approve or Reject buttons
- **Bulk**: Check the boxes next to entries (or "Select All"), then click "Approve Selected" or "Reject Selected"

When you **approve** an entry:
- It must have a **client** and **cost code** assigned (you'll be prompted to add them if missing)
- A **labor cost entry** is automatically created for job costing (hours x rate x burden multiplier)
- The entry counts toward the rep's payroll

When you **reject** an entry:
- You can enter a reason (the rep will see it)
- Any associated cost entry is removed

You can also **reset an entry back to Pending** if you need to change your decision.

### Payroll Tables

**Current Period Payroll** — For each employee:

| Column | What It Shows |
|--------|--------------|
| Employee | Click to see their detailed entries |
| Hours | Approved hours this period |
| Pending | How many entries still need approval |
| Rate | Hourly rate |
| Gross Pay | Hours x Rate |
| Costed | Burdened labor amount posted to jobs |
| Variance | Gross Pay minus Costed — flags unallocated time |

If the **Variance** column shows an amber dollar amount, it means some of that employee's approved time hasn't been allocated to a job (missing client or cost code). A green checkmark means all time is fully costed.

**Next Period Preview** — Tentative hours and pay for the upcoming pay period.

### Export Payroll CSV

Click **Export Payroll CSV** to download a spreadsheet of all approved entries for the period. The CSV includes columns mapped for QuickBooks import:

| CSV Column | Purpose |
|-----------|---------|
| Employee | Employee name |
| Date | Entry date (MM/DD/YYYY) |
| Hours | Hours worked |
| Hourly Rate | Base rate |
| Gross Pay | Hours x Rate |
| Burden Multiplier | The burden factor applied |
| Burdened Cost | Gross Pay x Burden Multiplier |
| Cost Code / Class | Maps to QuickBooks Class for job costing |
| Customer:Job | Maps to QuickBooks Customer for the client/project |
| Description | Work description |

---

## Job Costing

Job costing tracks how much labor is being spent on each client/project and compares it against budgets.

### How It Works

1. A rep logs time and tags it with a **client** and **cost code**
2. A supervisor **approves** the entry
3. The system automatically creates a **labor cost entry** = Hours x Rate x Burden Multiplier
4. These cost entries roll up by project and cost code

There is **no double entry** — the same approved time entry drives both payroll and job cost.

### Budget vs. Actual

Each project can have **budget lines** by cost code and cost type (Labor, Material, Subcontractor, Equipment, Other). When an estimate is accepted, budgets are auto-created. You can also set budgets manually.

Key metrics per project:
- **Budgeted** — total budget across all cost codes
- **Actual** — total cost entries posted
- **Budget Used %** — actual / budgeted (color-coded: green < 80%, amber 80-100%, red > 100%)
- **Cost to Complete (CTC)** — budgeted minus actual (how much is left)

### Labor Cost Reconciliation

On the Payroll Dashboard, the **Labor Cost Reconciliation** table shows each active project:

| Column | What It Shows |
|--------|--------------|
| Job / Client | The project name |
| Budgeted | Labor budget set for this project |
| Costed | Total burdened labor posted from approved time |
| Variance | Budget minus Costed — positive means under budget, negative means over |
| % Used | How much of the labor budget has been consumed |

**Color coding:**
- Over 100% used -> **red** (over budget)
- Over 80% used -> **amber** (approaching budget)
- Under 80% -> normal

**Click any row** to expand it and see the per-employee breakdown: who worked on that job, how many hours, their gross pay, and the burdened cost posted.

### Cost Codes

Cost codes are categories that describe what type of work was done. Examples:

- **01** — General Conditions
- **03** — Concrete / Foundation
- **06** — Framing / Rough Carpentry
- **16** — Electrical
- **17** — Plumbing

Supervisors manage cost codes in **Settings -> Cost Codes**. See the [Settings section](#cost-codes-1) below.

### Burden Multiplier

The burden multiplier accounts for the true cost of labor beyond the base hourly rate — payroll taxes, workers' comp, benefits, insurance, etc.

- **Default**: 1.25 (meaning a $20/hr employee actually costs the company $25/hr)
- **Company-wide setting**: Managed in Settings -> Cost Codes
- **Per-employee override**: Set on the employee's profile if someone has a different burden rate

**Example**: An employee earns $25/hr and works 8 hours on framing for a client.
- Gross pay: 8 x $25 = $200
- Burdened cost: $200 x 1.25 = $250 (this is what gets posted to the job)

---

## Reports

**Supervisors only.**

### Channel Spend

Track how much you're spending on each marketing channel per month.

- Select a month to view
- Add spend entries: pick a lead source, enter the amount, add an optional note
- See totals by source and the grand total for the month
- Meta Ads spend can be synced automatically (see Integrations)

### ROI Report

See the return on your marketing investment:

- **Total leads** generated in the period
- **Pipeline value** — total opportunity value of leads
- **Cost per lead** — marketing spend divided by number of leads
- **Cost per closed deal** — spend divided by deals that closed
- **ROI percentage** — return on marketing spend

Filter by date range (presets: this month, last month, last 3/12 months, or custom) and break down by lead source or by rep.

**Export**: Download the ROI data as a CSV for external analysis.

### Financial Reports

View project-level financial summaries:

- **Budget vs. Actual** by project and cost code
- **Cost to Complete** projections
- **Contract value** vs. billed vs. paid across all projects

---

## Client Portal

Clients get their own portal to view project progress, documents, selections, photos, and messages — without needing a staff login.

### How Clients Access It

1. A supervisor creates a **Client User** (email + name) linked to a client record
2. The system sends a **magic link** via email
3. The client clicks the link to access their portal — no password required
4. Magic links are **one-time use** and expire after 30 minutes
5. Once logged in, the session persists until they close the browser

### What Clients See

- **Dashboard** — project overview and recent updates
- **Documents** — files shared by the team
- **Selections** — material/finish selections to review and approve (e.g., flooring, countertops, paint colors)
- **Messages** — two-way messaging with the project team
- **Progress** — construction progress updates and milestones
- **Photos** — project photos organized by category

### Security

- Client sessions are **completely isolated** from staff sessions — a client login cannot access any staff route
- Each client only sees their own data — Client A cannot see Client B's messages, documents, or selections
- Inactive client users are blocked from accessing the portal
- Staff sessions cannot access the portal as a client

---

## Notification Preferences

Configure which notifications you receive. Go to your **profile -> Notification Settings**.

### Task Notifications

| Setting | What It Controls |
|---------|-----------------|
| Task Assigned | When you're assigned to a schedule task |
| Task Changed | When a task you're on is updated |
| Task Reminder | Daily reminders for upcoming tasks |

### Financial Notifications

| Setting | What It Controls |
|---------|-----------------|
| Invoice Created | When a new invoice is created |
| Payment Received | When a payment is recorded |
| Estimate Accepted | When a client accepts an estimate |

### Client Portal Notifications

| Setting | What It Controls |
|---------|-----------------|
| Portal Message | When a client sends a message through the portal |
| Selection Made | When a client makes a material/finish selection |

All notifications appear in the **bell icon** in the nav bar. Toggle each setting on or off based on your preferences.

---

## Settings & Administration

**Supervisors only** (except Profile, which all users can access).

### Profile

All users can edit their own profile:
- Name, phone, address
- Profile picture (upload or drag and drop)

Supervisors can additionally edit any user's profile, including their hourly rate and role.

### Manage Users

**Settings -> Manage Users**

**Adding a new user:**
1. Enter their Google email address
2. Set their role (Rep or Supervisor) and hourly rate
3. Click Add — they're now authorized
4. When they sign in with that Google email for the first time, their account is created with the role and rate you set

**Active users table** shows everyone who has logged in, with their role, rate, and last login date.

**Authorized users table** shows pending invitations (emails added but the person hasn't logged in yet).

### Cost Codes

**Settings -> Cost Codes**

Manage the cost codes used to tag time entries for job costing:
- **Add a code**: Enter a short code (e.g., "06"), a name (e.g., "Framing"), a default cost type (Labor, Material, etc.), and a sort order
- **Toggle active/inactive**: Deactivate codes you no longer use (they stop appearing in dropdowns but existing data is preserved)
- **Burden multiplier**: Set the company-wide default here (e.g., 1.25). Individual employees can have an override set on their profile.

### Lead Sources

**Settings -> Lead Sources**

Manage where your leads come from:
- Add new sources (e.g., "Angi", "Houzz")
- Assign a channel type: Paid Ads, Organic Social, Website, Phone, Referral, or Other
- Toggle sources active/inactive
- **Seed defaults**: If starting fresh, click to create the standard set (Google Ads, Meta Ads, Instagram, Facebook, Referral, etc.)
- **Backfill**: If older clients are missing their lead source, use the backfill page to assign them in bulk

### Integrations

**Settings -> Integrations**

Connect external platforms:

**GoHighLevel (GHL)**
- Connect your GHL account with an API key and location ID
- Test the connection to verify it works
- **Sync contacts**: Pull all GHL contacts into the app as new client leads
- Map imported contacts to a lead source (e.g., "GHL Import")
- Prevents duplicates — contacts already imported (by GHL ID) are skipped

**Meta Ads**
- Connect with your Meta access token and ad account ID
- Test the connection
- **Sync spend**: Pull this month's ad spend into the Channel Spend report automatically
- View campaign-level breakdown of spend

---

## Roles & Permissions

There are three identity types: **Rep**, **Supervisor**, and **Client (Portal)**.

| Feature | Rep | Supervisor | Client |
|---------|:---:|:----------:|:------:|
| View own clients | Yes | Yes | — |
| View all clients | — | Yes | — |
| Create/edit clients | Yes | Yes | — |
| Reassign clients | — | Yes | — |
| Create/manage estimates | Yes | Yes | — |
| Accept estimates | — | Yes | — |
| Create/manage schedules | Yes | Yes | — |
| Create daily logs | Yes | Yes | — |
| Create change orders | Yes | Yes | — |
| Approve change orders | — | Yes | — |
| Create/manage invoices | — | Yes | — |
| Clock in/out and log time | Yes | Yes | — |
| View own time logs | Yes | Yes | — |
| Approve/reject time entries | — | Yes | — |
| View payroll dashboard | — | Yes | — |
| Export payroll CSV | — | Yes | — |
| View reports (ROI, spend, financials) | — | Yes | — |
| Manage users | — | Yes | — |
| Manage settings | — | Yes | — |
| Edit own profile | Yes | Yes | — |
| Edit any profile | — | Yes | — |
| View portal dashboard | — | — | Yes |
| View/send portal messages | — | — | Yes |
| Make selections | — | — | Yes |
| View documents & photos | — | — | Yes |

---

## PWA / Mobile Install

The app is a **Progressive Web App (PWA)** — you can install it on your phone's home screen for a native app-like experience.

### Installing on iPhone (Safari)

1. Open the app in Safari
2. Tap the **Share** button (square with arrow)
3. Scroll down and tap **"Add to Home Screen"**
4. Tap **Add**

### Installing on Android (Chrome)

1. Open the app in Chrome
2. Tap the **three-dot menu** (top right)
3. Tap **"Add to Home Screen"** or **"Install App"**
4. Tap **Install**

### Offline Support

The app works offline for basic browsing — cached pages load even without internet. When you perform actions offline (submitting forms, logging time), they're saved in a local queue and automatically synced when you're back online.

An **"You're offline"** banner appears at the top when your connection drops, and disappears when it's restored.

---

## Key Concepts

### Pay Periods

Pay periods run on a semi-monthly schedule:
- **1st - 14th** of each month -> paid on the **15th**
- **15th - end of month** -> paid on the **1st** of the next month

All payroll calculations, exports, and dashboard views default to the current pay period.

### Time Zones

- All times are stored in **UTC** internally
- All times are displayed in **Pacific Time** (PT)
- Dates and times appear in **MM/DD/YYYY** and **12-hour AM/PM** format

### Approval Workflow

```
Rep logs time  ->  Entry created as PENDING
                        |
              Supervisor reviews on Payroll Dashboard
                   |              |
              APPROVED         REJECTED (with reason)
                 |                 |
         Counts toward pay    Rep sees rejection
         Cost entry posted    No pay / no cost entry
         to the job
```

Only **approved** entries count toward payroll and job costing. Supervisors can reset an approved or rejected entry back to pending if needed.

### Audit Trail

Financial and client-facing actions are logged automatically on the client timeline:
- Estimate accepted (with contract value)
- Invoice created or voided (with amounts)
- Change order approved (with cost impact)
- Status changes
- Daily logs finalized

### File Storage

Files (property images, activity attachments, profile pictures, daily log photos) are stored in **Cloudflare R2** cloud storage. Upload limits are 5 MB per file. Supported image formats: JPG, PNG, GIF, WebP.
