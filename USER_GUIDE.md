# All Inclusive ADU Portal — User Guide

A web app built for the All Inclusive ADU sales and construction team. It combines a **CRM** (client/lead management), **time tracking with payroll**, **job costing**, **reporting**, and **integrations** — all in one place, optimized for mobile.

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [The Hub (Home Dashboard)](#the-hub)
3. [Clients & CRM](#clients--crm)
4. [Time Tracking](#time-tracking)
5. [My Time Logs](#my-time-logs)
6. [Payroll Dashboard (Supervisors)](#payroll-dashboard)
7. [Job Costing](#job-costing)
8. [Reports](#reports)
9. [Settings & Administration](#settings--administration)
10. [Roles & Permissions](#roles--permissions)
11. [Key Concepts](#key-concepts)

---

## Getting Started

### Logging In

Sign in with your company Google account. The app uses Google login — no separate password needed.

- **First-time users**: A supervisor must add your Google email to the authorized users list before you can log in. Once added, just click "Sign in with Google."
- **Switching accounts**: Use "Fresh Login" from the profile menu to sign in with a different Google account.

### Navigation

The top bar has links to every section:

| Link | What It Does |
|------|-------------|
| **Hub** | Your home dashboard — weekly snapshot of clients, follow-ups, and activity |
| **Time** | Clock in/out and log hours |
| **Clients** | View and manage your client list |
| **Reports** | Channel spend and ROI analytics (supervisors only) |
| **Settings** | User management, cost codes, integrations (supervisors only) |

On mobile, tap the menu icon (three lines) to see these links.

There's also a **search bar** at the top — type a client name to jump straight to their record.

---

## The Hub

Your home dashboard. It shows a weekly snapshot — not a daily tool. Check it at the start of the week to know where you stand.

### What You See (Reps)

- **Your clients** broken down by status: Leads, Prospects, Active, Completed, On Hold — with total opportunity values
- **Recent clients** — the 5 most recently created
- **Upcoming follow-ups** — next steps you've scheduled on client activities
- **Recent activity** — your latest logged calls, meetings, notes
- **Weekly performance** — new leads, value added, conversations, and meetings this week vs. last week

### What You See (Supervisors)

Everything above, plus:

- **Filter by rep** — dropdown to view any rep's dashboard, or the whole company
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
- Every status change (Lead → Prospect → Active, etc.)
- All logged activities (calls, meetings, notes, site visits)
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

1. Go to **Time → Quick Log**
2. Enter the **date**, **hours** (in 15-minute increments: 0.25, 0.50, 0.75, etc.), **client**, and **description**
3. Optionally select a **cost code**
4. Submit — the entry is created as **Pending**

### How Hours Are Rounded

All hours are rounded to the nearest **15 minutes** (0.25 hours). For example:
- 1 hour 10 minutes → 1.00 hours
- 1 hour 15 minutes → 1.25 hours
- 2 hours 37 minutes → 2.50 hours

---

## My Time Logs

Go to **Time → My Logs** to see all your time entries.

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
- A **labor cost entry** is automatically created for job costing (hours × rate × burden multiplier)
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
| Gross Pay | Hours × Rate |
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
| Gross Pay | Hours × Rate |
| Burden Multiplier | The burden factor applied |
| Burdened Cost | Gross Pay × Burden Multiplier |
| Cost Code / Class | Maps to QuickBooks Class for job costing |
| Customer:Job | Maps to QuickBooks Customer for the client/project |
| Description | Work description |

---

## Job Costing

Job costing tracks how much labor is being spent on each client/project and compares it against budgets.

### How It Works

1. A rep logs time and tags it with a **client** and **cost code**
2. A supervisor **approves** the entry
3. The system automatically creates a **labor cost entry** = Hours × Rate × Burden Multiplier
4. These cost entries roll up by project and cost code

There is **no double entry** — the same approved time entry drives both payroll and job cost.

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
- Over 100% used → **red** (over budget)
- Over 80% used → **amber** (approaching budget)
- Under 80% → normal

**Click any row** to expand it and see the per-employee breakdown: who worked on that job, how many hours, their gross pay, and the burdened cost posted.

### Employee Cost Code Breakdown

A collapsible section showing how each employee's current-period hours break down across cost codes. Useful for seeing where each person's time is going.

### Cost Codes

Cost codes are categories that describe what type of work was done. Examples:

- **01** — General Conditions
- **03** — Concrete / Foundation
- **06** — Framing / Rough Carpentry
- **16** — Electrical
- **17** — Plumbing

Supervisors manage cost codes in **Settings → Cost Codes**. See the [Settings section](#cost-codes-1) below.

### Burden Multiplier

The burden multiplier accounts for the true cost of labor beyond the base hourly rate — payroll taxes, workers' comp, benefits, insurance, etc.

- **Default**: 1.25 (meaning a $20/hr employee actually costs the company $25/hr)
- **Company-wide setting**: Managed in Settings → Cost Codes
- **Per-employee override**: Set on the employee's profile if someone has a different burden rate

**Example**: An employee earns $25/hr and works 8 hours on framing for a client.
- Gross pay: 8 × $25 = $200
- Burdened cost: $200 × 1.25 = $250 (this is what gets posted to the job)

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

---

## Settings & Administration

**Supervisors only** (except Profile, which all users can access).

### Profile

All users can edit their own profile:
- Name, phone, address
- Profile picture (upload or drag and drop)

Supervisors can additionally edit any user's profile, including their hourly rate and role.

### Manage Users

**Settings → Manage Users**

**Adding a new user:**
1. Enter their Google email address
2. Set their role (Rep or Supervisor) and hourly rate
3. Click Add — they're now authorized
4. When they sign in with that Google email for the first time, their account is created with the role and rate you set

**Active users table** shows everyone who has logged in, with their role, rate, and last login date.

**Authorized users table** shows pending invitations (emails added but the person hasn't logged in yet).

### Cost Codes

**Settings → Cost Codes**

Manage the cost codes used to tag time entries for job costing:
- **Add a code**: Enter a short code (e.g., "06"), a name (e.g., "Framing"), a default cost type (Labor, Material, etc.), and a sort order
- **Toggle active/inactive**: Deactivate codes you no longer use (they stop appearing in dropdowns but existing data is preserved)
- **Burden multiplier**: Set the company-wide default here (e.g., 1.25). Individual employees can have an override set on their profile.

### Lead Sources

**Settings → Lead Sources**

Manage where your leads come from:
- Add new sources (e.g., "Angi", "Houzz")
- Assign a channel type: Paid Ads, Organic Social, Website, Phone, Referral, or Other
- Toggle sources active/inactive
- **Seed defaults**: If starting fresh, click to create the standard set (Google Ads, Meta Ads, Instagram, Facebook, Referral, etc.)
- **Backfill**: If older clients are missing their lead source, use the backfill page to assign them in bulk

### Integrations

**Settings → Integrations**

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

There are two roles: **Rep** and **Supervisor**.

| Feature | Rep | Supervisor |
|---------|:---:|:----------:|
| View own clients | Yes | Yes |
| View all clients | — | Yes |
| Create clients | Yes | Yes |
| Edit own clients | Yes | Yes |
| Edit any client | — | Yes |
| Reassign clients | — | Yes |
| Clock in/out and log time | Yes | Yes |
| View own time logs | Yes | Yes |
| Approve/reject time entries | — | Yes |
| View payroll dashboard | — | Yes |
| Export payroll CSV | — | Yes |
| View reports (ROI, spend) | — | Yes |
| Manage users | — | Yes |
| Manage settings | — | Yes |
| Edit own profile | Yes | Yes |
| Edit any profile | — | Yes |

---

## Key Concepts

### Pay Periods

Pay periods run on a semi-monthly schedule:
- **1st – 14th** of each month → paid on the **15th**
- **15th – end of month** → paid on the **1st** of the next month

All payroll calculations, exports, and dashboard views default to the current pay period.

### Time Zones

- All times are stored in **UTC** internally
- All times are displayed in **Pacific Time** (PT)
- Dates and times appear in **MM/DD/YYYY** and **12-hour AM/PM** format

### Approval Workflow

```
Rep logs time  →  Entry created as PENDING
                        ↓
              Supervisor reviews on Payroll Dashboard
                   ↓              ↓
              APPROVED         REJECTED (with reason)
                 ↓                 ↓
         Counts toward pay    Rep sees rejection
         Cost entry posted    No pay / no cost entry
         to the job
```

Only **approved** entries count toward payroll and job costing. Supervisors can reset an approved or rejected entry back to pending if needed.

### File Storage

Files (property images, activity attachments, profile pictures) are stored in **Cloudflare R2** cloud storage. Upload limits are 5 MB per file. Supported image formats: JPG, PNG, GIF, WebP.
