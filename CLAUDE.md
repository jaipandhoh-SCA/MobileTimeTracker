# CLAUDE.md

Flask + PostgreSQL (Neon) + SQLAlchemy CRM and time-tracking portal for an
ADU construction sales team. Jinja2 templates, Tailwind CDN, vanilla JS.
Google OAuth login (our own credentials), Cloudflare R2 for file storage.

Rules:
- PROJECT_PLAN.md is the source of truth for active work. FEATURE_ROADMAP.md
  is context/direction only — NOT a work order. Only build what's in
  PROJECT_PLAN.md Active or what Jai asks for directly.
- Update PROJECT_PLAN.md's Changelog when you ship something.
- Times: stored UTC, displayed Pacific. 12-hour AM/PM, MM/DD/YYYY, hours
  round to nearest 0.25.
- Mobile-first. The app is a weekly brief, not a daily tool — one-page hub
  design, minimal nav.
- Clock-in/time tracking is on probation: keep it working, build nothing
  new on it.
- Never commit .env* files or secrets.
- Ask before large refactors.
