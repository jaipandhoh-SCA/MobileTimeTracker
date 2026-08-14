/**
 * Demo Tour — guided walkthrough of every feature.
 *
 * Uses a spotlight overlay + tooltip card system.
 * Tour steps are organized by page. When a step says "navigate to X",
 * clicking Next will actually navigate the browser.
 */

(function () {
  'use strict';

  /* ───────────────────────── Tour Steps ───────────────────────── */

  // Each step: { page, target (CSS selector), title, text, position?, navigate? }
  // If navigate is set, clicking "Next" goes to that URL instead of advancing in-page.
  // target can be null for a centered "intro" card.

  const TOUR_STEPS = [
    // ── Hub / Dashboard ──────────────────────────────────────
    {
      page: 'home', target: null,
      title: 'Welcome to the ADU Portal',
      text: 'This is your Hub — a weekly snapshot of your pipeline, financials, and assignments. Let\'s walk through every feature.',
    },
    {
      page: 'home', target: 'nav',
      title: 'Navigation Bar',
      text: 'The nav bar gives you quick access to every module: Hub, Time, Clients, Estimates, Tasks, Logs, Change Orders, Reports, and Settings.',
      position: 'bottom',
    },
    {
      page: 'home', target: '[data-tour="pipeline-cards"], .space-y-4 > :nth-child(4), .grid',
      title: 'Pipeline Overview',
      text: 'Your pipeline cards show clients by status — Leads, Prospects, Active, Completed — with opportunity values. Click any card to filter the client list.',
      position: 'bottom',
    },
    {
      page: 'home', target: null,
      title: 'Let\'s see the Client List',
      text: 'Next, we\'ll look at how you manage clients. Click Next to go to the Clients page.',
      navigate: '/clients',
    },

    // ── Clients ──────────────────────────────────────────────
    {
      page: 'clients', target: null,
      title: 'Client List',
      text: 'Here you see all your clients. The list shows status, contact info, opportunity value, and assigned rep. Supervisors see everyone; reps see only their own.',
    },
    {
      page: 'clients', target: 'a[href*="/clients/create"], a[href*="/clients/new"]',
      title: 'Create a Client',
      text: 'Click "+ New Client" to add a lead. You\'ll fill in contact info, ADU details, budget, and timeline.',
      position: 'left',
    },
    {
      page: 'clients', target: 'table tbody tr:first-child, .divide-y > :first-child',
      title: 'Open a Client Record',
      text: 'Click any client row to see their full record — timeline, activities, project details, documents, and more. Let\'s open the demo client.',
      position: 'bottom',
      navigateToFirstDemoClient: true,
    },

    // ── Client Record ────────────────────────────────────────
    {
      page: 'client_detail', target: null,
      title: 'Client Record',
      text: 'This is the heart of the CRM. Everything about a client lives here: timeline, activities, project status, and quick actions.',
    },
    {
      page: 'client_detail', target: '[data-tour="timeline"], .space-y-3, #timeline',
      title: 'Activity Timeline',
      text: 'Every interaction is logged — calls, meetings, site visits, status changes, estimates, invoices. This is a complete audit trail.',
      position: 'top',
    },
    {
      page: 'client_detail', target: null,
      title: 'Next: Estimates',
      text: 'Let\'s look at how you create detailed construction estimates. Click Next to continue.',
      navigate: '/estimates',
    },

    // ── Estimates ─────────────────────────────────────────────
    {
      page: 'estimates', target: null,
      title: 'Estimates',
      text: 'Estimates are detailed cost breakdowns for ADU projects. You can start from a template (Studio, 1BR, 2BR, etc.) or build from scratch.',
    },
    {
      page: 'estimates', target: 'table tbody tr:first-child, .divide-y > :first-child',
      title: 'Estimate Records',
      text: 'Each estimate shows the client, ADU type, total amount, and status (Draft, Sent, Accepted, Rejected). Click one to see the full breakdown.',
      position: 'bottom',
      navigateToFirstEstimate: true,
    },

    // ── Estimate Detail ──────────────────────────────────────
    {
      page: 'estimate_detail', target: null,
      title: 'Estimate Breakdown',
      text: 'Line items are organized by cost code. Each shows quantity, unit cost, labor/material split, and waste factor. The math auto-calculates subtotal, overhead, markup, and contingency.',
    },
    {
      page: 'estimate_detail', target: null,
      title: 'Next: Scheduling',
      text: 'Once an estimate is accepted and a contract is signed, the project gets scheduled. Let\'s look at the scheduling system.',
      navigateToSchedule: true,
    },

    // ── Schedule ─────────────────────────────────────────────
    {
      page: 'schedule', target: null,
      title: 'Project Schedule',
      text: 'The schedule shows tasks organized into phases (Site Prep, Framing, MEP, Finishes). You\'re viewing a Gantt-style timeline of the demo project.',
    },
    {
      page: 'schedule', target: null,
      title: 'Next: My Tasks',
      text: 'Each team member can see their assigned tasks. Let\'s check the My Tasks view.',
      navigate: '/my-tasks',
    },

    // ── My Tasks ─────────────────────────────────────────────
    {
      page: 'my_tasks', target: null,
      title: 'My Tasks',
      text: 'This mobile-friendly view shows your tasks grouped by today, this week, and overdue. You can update task status directly from here.',
    },
    {
      page: 'my_tasks', target: null,
      title: 'Next: Daily Logs',
      text: 'Field crews document their daily work with logs. Let\'s see.',
      navigate: '/daily-logs',
    },

    // ── Daily Logs ───────────────────────────────────────────
    {
      page: 'daily_logs', target: null,
      title: 'Daily Field Logs',
      text: 'Logs capture crew info, hours, work performed, weather (auto-fetched), delays, and photos. They can be exported as PDFs and shared with clients.',
    },
    {
      page: 'daily_logs', target: null,
      title: 'Next: Change Orders',
      text: 'When scope changes happen during construction, you create change orders. Let\'s look.',
      navigate: '/change-orders',
    },

    // ── Change Orders ────────────────────────────────────────
    {
      page: 'change_orders', target: null,
      title: 'Change Orders',
      text: 'Change orders track scope additions or modifications. They have line items with cost codes, and when approved, they update the project\'s contract value and budget.',
    },
    {
      page: 'change_orders', target: 'table tbody tr:first-child, .divide-y > :first-child',
      title: 'Example Change Order',
      text: 'The demo shows a quartz countertop upgrade — approved by the client with line items totaling $4,800. This was linked to a client portal selection.',
      position: 'bottom',
    },
    {
      page: 'change_orders', target: null,
      title: 'Next: Time Tracking',
      text: 'The app includes time tracking with clock in/out and quick logging. Let\'s take a look.',
      navigate: '/my-logs',
    },

    // ── My Logs (Time) ───────────────────────────────────────
    {
      page: 'my_logs', target: null,
      title: 'Time Tracking — My Logs',
      text: 'Reps clock in/out or quick-log hours. Entries show the date, client, cost code, hours, and status. Supervisors approve or reject each entry.',
    },
    {
      page: 'my_logs', target: null,
      title: 'Next: Payroll',
      text: 'Approved time entries flow into the payroll dashboard. Let\'s see the supervisor view.',
      navigate: '/admin',
    },

    // ── Payroll / Admin ──────────────────────────────────────
    {
      page: 'admin', target: null,
      title: 'Payroll Dashboard',
      text: 'Supervisors see pending approvals, payroll summaries per employee, and labor cost reconciliation per project. Approved hours × rate × burden = burdened cost posted to jobs.',
    },
    {
      page: 'admin', target: null,
      title: 'Next: Reports',
      text: 'The reporting module tracks marketing ROI and project financials.',
      navigate: '/reports/channel-spend',
    },

    // ── Reports ──────────────────────────────────────────────
    {
      page: 'reports', target: null,
      title: 'Channel Spend',
      text: 'Track marketing spend by channel per month. Meta Ads spend can sync automatically. This feeds into the ROI report.',
    },
    {
      page: 'reports', target: null,
      title: 'Next: ROI Report',
      text: 'Let\'s see the ROI calculations.',
      navigate: '/reports/roi',
    },
    {
      page: 'roi_report', target: null,
      title: 'ROI Report',
      text: 'See total leads, pipeline value, cost per lead, cost per deal, and ROI percentage — broken down by lead source or rep. Export as CSV.',
    },
    {
      page: 'roi_report', target: null,
      title: 'Next: Settings',
      text: 'Let\'s look at the admin settings.',
      navigate: '/settings/cost-codes',
    },

    // ── Settings ─────────────────────────────────────────────
    {
      page: 'settings', target: null,
      title: 'Settings — Cost Codes',
      text: 'Manage cost codes, burden multiplier, lead sources, integrations (GHL, Meta, QuickBooks), and user access. Cost codes drive all job costing throughout the system.',
    },
    {
      page: 'settings', target: null,
      title: 'Tour Complete!',
      text: 'You\'ve seen every major feature: CRM, Estimating, Scheduling, Daily Logs, Change Orders, Time Tracking, Payroll, Billing, Reports, and Settings. Click "Exit Demo" in the banner to remove sample data, or keep exploring!',
      isFinal: true,
    },
  ];

  /* ───────────────────────── State ────────────────────────── */

  let currentStep = parseInt(sessionStorage.getItem('demoTourStep') || '0', 10);
  let overlay, spotlight, tooltip;

  /* ───────────────────────── DOM Setup ─────────────────────── */

  function createOverlay() {
    // Backdrop
    overlay = document.createElement('div');
    overlay.id = 'demo-tour-overlay';
    overlay.style.cssText = `
      position: fixed; inset: 0; z-index: 9998;
      background: rgba(15, 23, 42, 0.55);
      transition: opacity 0.3s ease;
      pointer-events: auto;
    `;

    // Spotlight cutout (positioned over target)
    spotlight = document.createElement('div');
    spotlight.id = 'demo-tour-spotlight';
    spotlight.style.cssText = `
      position: fixed; z-index: 9999;
      border-radius: 12px;
      box-shadow: 0 0 0 9999px rgba(15, 23, 42, 0.55);
      transition: all 0.4s cubic-bezier(0.4, 0, 0.2, 1);
      pointer-events: none;
    `;

    // Tooltip card
    tooltip = document.createElement('div');
    tooltip.id = 'demo-tour-tooltip';
    tooltip.style.cssText = `
      position: fixed; z-index: 10000;
      background: white; border-radius: 16px;
      box-shadow: 0 4px 32px rgba(0,0,0,0.18);
      padding: 24px; max-width: 380px; width: 90vw;
      font-family: ui-sans-serif, system-ui, sans-serif;
      transition: all 0.35s cubic-bezier(0.4, 0, 0.2, 1);
    `;

    document.body.appendChild(overlay);
    document.body.appendChild(spotlight);
    document.body.appendChild(tooltip);

    overlay.addEventListener('click', function (e) {
      e.stopPropagation();
    });
  }

  function renderStep(step, index) {
    const total = TOUR_STEPS.length;
    const progress = Math.round(((index + 1) / total) * 100);

    tooltip.innerHTML = `
      <div style="margin-bottom: 12px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px;">
          <span style="font-size: 11px; font-weight: 600; color: #D6246E; text-transform: uppercase; letter-spacing: 0.05em;">
            Step ${index + 1} of ${total}
          </span>
          <button id="tour-close" style="background: none; border: none; cursor: pointer; padding: 4px; color: #94a3b8; font-size: 18px;" title="Close tour">&times;</button>
        </div>
        <div style="height: 3px; background: #f1f5f9; border-radius: 2px; overflow: hidden;">
          <div style="height: 100%; width: ${progress}%; background: #D6246E; border-radius: 2px; transition: width 0.4s;"></div>
        </div>
      </div>
      <h3 style="font-size: 18px; font-weight: 700; color: #0f172a; margin: 0 0 8px 0; line-height: 1.3;">
        ${step.title}
      </h3>
      <p style="font-size: 14px; color: #475569; margin: 0 0 20px 0; line-height: 1.6;">
        ${step.text}
      </p>
      <div style="display: flex; gap: 8px; justify-content: flex-end; align-items: center;">
        ${index > 0 ? '<button id="tour-prev" style="padding: 8px 16px; border-radius: 8px; border: 1px solid #e2e8f0; background: white; color: #475569; font-size: 13px; font-weight: 500; cursor: pointer;">Back</button>' : ''}
        ${step.isFinal
          ? '<a href="/demo/exit" style="padding: 8px 20px; border-radius: 8px; background: #0f172a; color: white; font-size: 13px; font-weight: 600; text-decoration: none; text-align: center;">Exit Demo</a>'
          : `<button id="tour-next" style="padding: 8px 20px; border-radius: 8px; background: #D6246E; color: white; border: none; font-size: 13px; font-weight: 600; cursor: pointer;">
              ${step.navigate || step.navigateToFirstDemoClient || step.navigateToFirstEstimate || step.navigateToSchedule ? 'Next →' : 'Next'}
            </button>`
        }
      </div>
    `;

    // Event listeners
    const closeBtn = document.getElementById('tour-close');
    if (closeBtn) closeBtn.addEventListener('click', closeTour);

    const prevBtn = document.getElementById('tour-prev');
    if (prevBtn) prevBtn.addEventListener('click', prevStep);

    const nextBtn = document.getElementById('tour-next');
    if (nextBtn) nextBtn.addEventListener('click', function () { nextStep(step); });
  }

  function positionTooltip(step) {
    if (!step.target) {
      // Center on screen
      spotlight.style.display = 'none';
      overlay.style.background = 'rgba(15, 23, 42, 0.55)';
      tooltip.style.top = '50%';
      tooltip.style.left = '50%';
      tooltip.style.transform = 'translate(-50%, -50%)';
      return;
    }

    const el = document.querySelector(step.target);
    if (!el) {
      // Target not found — center tooltip instead
      spotlight.style.display = 'none';
      overlay.style.background = 'rgba(15, 23, 42, 0.55)';
      tooltip.style.top = '50%';
      tooltip.style.left = '50%';
      tooltip.style.transform = 'translate(-50%, -50%)';
      return;
    }

    // Scroll element into view
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });

    // Wait for scroll to settle
    setTimeout(function () {
      const rect = el.getBoundingClientRect();
      const pad = 8;

      // Position spotlight
      overlay.style.background = 'transparent';
      spotlight.style.display = 'block';
      spotlight.style.top = (rect.top - pad) + 'px';
      spotlight.style.left = (rect.left - pad) + 'px';
      spotlight.style.width = (rect.width + pad * 2) + 'px';
      spotlight.style.height = (rect.height + pad * 2) + 'px';

      // Position tooltip
      tooltip.style.transform = 'none';
      const pos = step.position || 'bottom';
      const ttWidth = Math.min(380, window.innerWidth * 0.9);

      if (pos === 'bottom') {
        tooltip.style.top = (rect.bottom + pad + 12) + 'px';
        tooltip.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - ttWidth - 8)) + 'px';
      } else if (pos === 'top') {
        tooltip.style.top = Math.max(8, rect.top - pad - 220) + 'px';
        tooltip.style.left = Math.max(8, Math.min(rect.left, window.innerWidth - ttWidth - 8)) + 'px';
      } else if (pos === 'left') {
        tooltip.style.top = rect.top + 'px';
        tooltip.style.left = Math.max(8, rect.left - ttWidth - 16) + 'px';
      } else {
        tooltip.style.top = rect.top + 'px';
        tooltip.style.left = (rect.right + 16) + 'px';
      }

      // Keep tooltip on screen
      const ttRect = tooltip.getBoundingClientRect();
      if (ttRect.bottom > window.innerHeight - 8) {
        tooltip.style.top = Math.max(8, window.innerHeight - ttRect.height - 8) + 'px';
      }
      if (ttRect.right > window.innerWidth - 8) {
        tooltip.style.left = Math.max(8, window.innerWidth - ttRect.width - 8) + 'px';
      }
    }, 350);
  }

  /* ───────────────────────── Navigation ───────────────────── */

  function showStep(index) {
    if (index < 0 || index >= TOUR_STEPS.length) return;
    currentStep = index;
    sessionStorage.setItem('demoTourStep', index);
    const step = TOUR_STEPS[index];
    renderStep(step, index);
    positionTooltip(step);

    // Persist to server
    fetch('/demo/tour/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step: index, page: step.page }),
    }).catch(function () {});
  }

  function nextStep(step) {
    // Handle navigation steps
    if (step.navigate) {
      sessionStorage.setItem('demoTourStep', currentStep + 1);
      window.location.href = step.navigate;
      return;
    }
    if (step.navigateToFirstDemoClient) {
      sessionStorage.setItem('demoTourStep', currentStep + 1);
      // Find the first demo client link
      const link = document.querySelector('a[href*="/clients/"][href$="/edit"]');
      const row = document.querySelector('table tbody tr:first-child a, .divide-y a[href*="/clients/"]');
      if (row) {
        window.location.href = row.getAttribute('href');
      } else {
        window.location.href = '/clients';
      }
      return;
    }
    if (step.navigateToFirstEstimate) {
      sessionStorage.setItem('demoTourStep', currentStep + 1);
      const row = document.querySelector('table tbody tr:first-child a, .divide-y a[href*="/estimates/"]');
      if (row) {
        window.location.href = row.getAttribute('href');
      } else {
        showStep(currentStep + 1);
      }
      return;
    }
    if (step.navigateToSchedule) {
      sessionStorage.setItem('demoTourStep', currentStep + 1);
      // Find active project schedule link
      const link = document.querySelector('a[href*="/schedule/"]');
      if (link) {
        window.location.href = link.getAttribute('href');
      } else {
        // Try to find the project ID from the page
        window.location.href = '/my-tasks';
        sessionStorage.setItem('demoTourStep', currentStep + 2);
      }
      return;
    }

    showStep(currentStep + 1);
  }

  function prevStep() {
    showStep(currentStep - 1);
  }

  function closeTour() {
    sessionStorage.removeItem('demoTourStep');
    if (overlay) overlay.remove();
    if (spotlight) spotlight.remove();
    if (tooltip) tooltip.remove();
    // Don't exit demo mode — just close the tour overlay
    // User can re-trigger from the demo banner or exit demo entirely
  }

  /* ───────────────────── Page Detection ───────────────────── */

  function detectCurrentPage() {
    const path = window.location.pathname;
    if (path === '/home' || path === '/') return 'home';
    if (path === '/clients') return 'clients';
    if (/^\/clients\/\d+/.test(path)) return 'client_detail';
    if (path === '/estimates') return 'estimates';
    if (/^\/estimates\/\d+$/.test(path)) return 'estimate_detail';
    if (/^\/schedule\//.test(path)) return 'schedule';
    if (path === '/my-tasks') return 'my_tasks';
    if (path === '/daily-logs') return 'daily_logs';
    if (path === '/change-orders') return 'change_orders';
    if (path === '/my-logs') return 'my_logs';
    if (path === '/admin') return 'admin';
    if (path.includes('/channel-spend')) return 'reports';
    if (path.includes('/roi')) return 'roi_report';
    if (path.includes('/settings') || path.includes('/admin/users')) return 'settings';
    return null;
  }

  function findFirstStepForPage(pageName) {
    for (let i = 0; i < TOUR_STEPS.length; i++) {
      if (TOUR_STEPS[i].page === pageName) return i;
    }
    return -1;
  }

  /* ───────────────────────── Init ─────────────────────────── */

  function init() {
    // Only run if demo mode is active (set by the banner element)
    if (!document.getElementById('demo-banner')) return;

    createOverlay();

    // Determine which step to show
    const savedStep = parseInt(sessionStorage.getItem('demoTourStep') || '0', 10);
    const currentPage = detectCurrentPage();

    if (savedStep > 0 && savedStep < TOUR_STEPS.length) {
      // Check if the saved step's page matches the current page
      const savedPage = TOUR_STEPS[savedStep].page;
      if (savedPage === currentPage) {
        showStep(savedStep);
      } else {
        // We navigated — find the first step for this page
        const pageStep = findFirstStepForPage(currentPage);
        if (pageStep >= 0) {
          showStep(pageStep);
        } else {
          showStep(savedStep);
        }
      }
    } else {
      showStep(0);
    }

    // Re-trigger tour from banner button
    const restartBtn = document.getElementById('demo-restart-tour');
    if (restartBtn) {
      restartBtn.addEventListener('click', function (e) {
        e.preventDefault();
        if (!overlay) createOverlay();
        else {
          document.body.appendChild(overlay);
          document.body.appendChild(spotlight);
          document.body.appendChild(tooltip);
        }
        const pageStep = findFirstStepForPage(detectCurrentPage());
        showStep(pageStep >= 0 ? pageStep : 0);
      });
    }
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
