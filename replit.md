# All Inclusive ADU Portal

## Overview
A mobile-first web application for All Inclusive ADU sales representatives to track time, manage clients, and log activities. It provides supervisor oversight, payroll tracking, and CRM functionalities. The project's vision is to streamline operations for ADU sales teams, offering a comprehensive tool from lead management to payroll.

## User Preferences
- **Communication Style**: Clear, concise, and direct.
- **Workflow**: Iterative development with a focus on core features first.
- **Interaction**: Ask for confirmation before implementing major changes or refactoring large sections of code.
- **Timezone**: Pacific Time (PST/PDT) for all users
- **Time Format**: 12-hour with AM/PM
- **Date Format**: MM/DD/YYYY
- **Hours Rounding**: Nearest 0.25 (15 minute increments)

## System Architecture

### UI/UX Decisions
The application prioritizes a mobile-first, responsive design using Tailwind CSS. Key UI/UX features include:
- **Dashboard-style Home Page**: Personalized views for reps and supervisors, displaying opportunities, recent clients, next steps, and activity.
    - **Supervisor Dashboard**: Shows "Company Opportunities" with aggregated data from all users. Includes a user filter dropdown to view individual rep's data. Recent Clients and Recent Activity sections (limited to 5 items each) appear below the opportunities cards.
    - **Rep Dashboard**: Shows "My Opportunities" with only their assigned clients and activities. Recent Clients and Recent Activity sections (limited to 5 items each) appear below the opportunities cards.
    - **User Filter**: Supervisors can select "All Company Data" or specific users from a dropdown, which refreshes the page to show filtered data.
- **Redesigned Client Pages**: Read-only client details by default with an "Edit" button, responsive layouts adapting to screen size, and dynamic, auto-saving status updates.
- **Admin Dashboard Layout**: Left sidebar with filters (From/To Date, Rep, Client), main content area with dual pay period display:
    - **Current Pay Period** (green): Always visible, shows current pay period totals for all reps
    - **Filtered Period Summary** (blue): Appears below Current Pay Period when filters are applied, displays payroll totals based on selected date range, rep, and client filters to help calculate custom paycheck amounts. Rep names are clickable to view individual rep detail pages with time entries and editing capabilities.
- **Rep Time Entries Page**: Left sidebar with filters (From/To Date, Client), main content area shows both Current and Upcoming pay period summaries at the top, followed by time entries list with expandable details and correction note functionality.
- **Individual Rep Detail Page (Supervisors)**: Similar layout to rep's page but for viewing a specific rep's data. Shows current pay period summary, stats cards, and time entries table with edit capabilities.
- **Color-coded Statuses**: Visual cues for client status and next steps.

### Technical Implementations
- **Core Functionality**: User authentication, clock in/out with live timers, manual time entry, and client management.
- **Break Tracking**: 15-minute break (available after 1 hour) and 1-hour lunch (available after 2 hours) buttons automatically deduct time from shift totals.
- **Payroll Tracking**: Includes hourly rates, defined pay periods (1st-14th, 15th-end of month), and an admin dashboard for payroll oversight.
- **Client Management (CRM)**: Comprehensive client profiles with contact persons, phone, email, statuses (Lead/Prospect/Active/Completed/On Hold/Lost), opportunity values, and notes.
    - **Opportunity Value Lock**: Opportunity value field is disabled until client status is set to "Active" to prevent premature funnel entries.
    - **Lost Status**: Black dot icon (⚫) with gray color scheme for tracking lost opportunities.
- **Property Details Tracking**: Extensive ADU property information including:
    - Property dimensions: lot size, square footage, existing square footage
    - Zoning information: residential zoning (R-1, R-1A, R-1B)
    - ADU specifications: type (Detached/Garage Conversion), desired ADU square footage, bedrooms, bathrooms, style, key features
    - Financial data: max budget, financing option (Cash/Loan), original property value, expected ROI, value increase, new property value
    - Project timeline: estimated start date, estimated end date
    - Permitting status: Pending/Approved/Denied with color-coded badges
    - Google Maps integration for property addresses
    - **Collapsible UI**: Property Details section collapses to save screen space on mobile devices
- **Property Images**: Photo gallery for property walk-throughs and site visits
    - **Drag-and-Drop Upload**: Easy image upload with visual drag-and-drop interface
    - **Image-Only Validation**: Accepts only image files (JPG, PNG, GIF, WebP) up to 16MB each
    - **Gallery View**: Responsive grid layout (2 columns mobile, 3 columns desktop)
    - **Hover-to-Delete**: Delete images with hover-activated delete buttons
    - **Collapsible Section**: Property Images collapses to keep New Activity visible on mobile
    - **Google Drive Integration**: All property images are now stored in Google Drive with automatic folder organization
- **Client Activity Log**: Time-stamped activity tracking with various types (e.g., Spoke to, Meeting, Email sent), file attachments (up to 16MB), and next steps with scheduled dates.
    - **Google Drive Storage**: All activity attachments are stored in Google Drive for centralized file management
- **User Authorization**: Controls who can access the application through an authorized users list.
    - First user to sign in automatically becomes a supervisor
    - Supervisors can add authorized email addresses through the Manage Users page
    - Unauthorized users see an "Access Denied" page when attempting to sign in
    - **Google OAuth Authentication**: Direct Google OAuth implementation with `prompt=select_account` parameter
        - Every login shows Google account chooser, enabling seamless multi-user switching
        - No incognito mode required to switch between authorized accounts
        - Professional Google Sign-In branding on landing page
        - Secure OAuth 2.0 flow with client credentials stored as environment secrets
- **Role-Based Access**: Differentiates between 'Rep' and 'Supervisor' roles with distinct permissions and data visibility.
    - **Rep**: Manages own time logs, clients assigned to them, and client activities.
    - **Supervisor**: Full visibility over all reps' data, manages user roles, can edit any time entry, reassign clients, activate/deactivate clients, edit user profiles, and remove users.
    - **User Management**: Supervisors can click on user names in Manage Users page to edit any user's profile details including role, hourly rate, and contact information.
    - **Client Reassignment**: Before removing a user with assigned clients, supervisors must select another user to reassign those clients to via a modal dialog.
    - **User Removal**: Red "Remove User" button on Edit User Profile page with confirmation prompts and automatic cascade deletion of time entries and data cleanup.
- **Profile Management**: WordPress-like profile editing interface for reps and supervisors.
    - **View Mode**: Displays profile details with clickable hyperlinks for email (mailto:) and phone (tel:) for easy contact.
    - **Edit Mode**: Required fields for first name, last name, email, phone, and address with client-side validation.
    - **Profile Picture Upload**: Drag-and-drop interface for uploading custom profile pictures (JPG, PNG, GIF, WebP - Max 5MB). Images display in navigation dropdown and profile page.
    - **User Dropdown Menu**: Navigation dropdown with "Howdy, [Name]" greeting, profile picture or initial, Edit Profile link, and Log Out option.
    - **User Model Fields**: Stores phone, address, and profile_image_url for each user along with existing name and contact details.
- **Data Export**: CSV export of filtered time logs.
- **Security**: CSRF protection implemented via Flask-WTF.
- **Timezone Handling**: All times stored in UTC and displayed in Pacific Time (America/Los_Angeles).

### System Design Choices
- **Separate ActiveClock table**: Ensures data integrity for concurrent time tracking.
- **Hardcoded PST timezone**: Simplifies initial development for a regional user base.
- **Inline client creation**: Improves workflow efficiency during time entry.
- **Correction notes**: Allows reps to communicate with supervisors regarding time entry adjustments without direct editing permissions.
- **Google Drive Integration**: Centralized file storage for property images and activity attachments
    - **Automatic Folder Creation**: The app automatically creates a "Property Files" folder in My Drive if it doesn't exist
    - **Automatic Client Folder Structure**: When a client is created, a folder structure is automatically created: "My Drive/Property Files/[Client Name - Address]/Property Images/Documents/Contracts"
    - **File Upload**: All new property images and activity attachments are uploaded to Google Drive instead of local storage
    - **Accordion-Style Uploaders**: Property Files cards (Property Images, Documents, Contracts) maintain their colored styling but are clickable to expand/collapse dedicated uploaders for each folder type
    - **Folder-Specific Upload Routing**: Each accordion uploader targets the correct Google Drive folder with appropriate file type restrictions (images for Property Images, docs/spreadsheets for Documents, PDF/DOC for Contracts)
    - **Sequential Multi-File Upload**: Drag-and-drop or select multiple files with progress tracking ("Uploading 1 of 5...") and automatic activity log creation
    - **Folder Sharing**: All Google Drive folders are configured as "Anyone with the link can view" for easy team collaboration
    - **Private Files**: Files remain private in Google Drive, accessible only through authenticated app users
    - **Backward Compatibility**: Legacy local files are still supported for viewing and downloading
    - **OAuth Authentication**: Uses Replit's Google Drive connector for secure OAuth authentication
    - **File Management**: Supports upload, view, and delete operations with automatic cleanup

## External Dependencies

- **Flask 3.x**: Web framework.
- **PostgreSQL (Neon-backed)**: Primary database.
- **SQLAlchemy 2.x**: Object-Relational Mapper (ORM).
- **Flask-Login**: User session management.
- **Google OAuth 2.0**: Direct Google authentication with oauthlib.oauth2.
- **Flask-WTF**: Forms and CSRF protection.
- **Jinja2**: Templating engine.
- **Tailwind CSS (CDN)**: Frontend styling.
- **Vanilla JavaScript**: For dynamic UI elements like live timers.
- **Google Drive API**: For centralized file storage (property images, documents, contracts).