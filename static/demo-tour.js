/**
 * Interactive Demo — context-aware hints + exploration checklist.
 *
 * Instead of a linear "next/next/next" tour, this system:
 * 1. Shows a page-specific hint card with suggested actions
 * 2. Tracks which features the user has actually visited
 * 3. Provides a collapsible checklist panel for progress
 * 4. Encourages clicking, not just reading
 */

(function () {
  'use strict';

  /* ═══════════════════════ Feature Checklist ═══════════════════════ */

  const FEATURES = [
    { id: 'hub',            label: 'Hub / Dashboard',    page: 'home',           path: '/home' },
    { id: 'clients',        label: 'Client List',        page: 'clients',        path: '/clients' },
    { id: 'client_detail',  label: 'Client Record',      page: 'client_detail',  path: null },
    { id: 'estimates',      label: 'Estimates',          page: 'estimates',      path: '/estimates' },
    { id: 'estimate_detail',label: 'Estimate Breakdown', page: 'estimate_detail',path: null },
    { id: 'schedule',       label: 'Project Schedule',   page: 'schedule',       path: null },
    { id: 'daily_logs',     label: 'Daily Logs',         page: 'daily_logs',     path: '/daily-logs' },
    { id: 'change_orders',  label: 'Change Orders',      page: 'change_orders',  path: '/change-orders' },
    { id: 'admin',          label: 'Payroll & Admin',    page: 'admin',          path: '/admin' },
    { id: 'reports',        label: 'Reports',            page: 'reports',        path: '/reports/channel-spend' },
  ];

  /* ═══════════════════════ Page Hints ═══════════════════════ */

  // Each page gets a context hint with suggested actions
  const PAGE_HINTS = {
    home: {
      title: 'Your Hub',
      text: 'This is your weekly snapshot. Pipeline cards, revenue, and attention items are all here.',
      actions: [
        { label: 'Check pipeline cards', desc: 'See lead counts and values by status' },
        { label: 'Review attention items', desc: 'Clients needing follow-up are flagged' },
        { label: 'Go to Clients', link: '/clients' },
      ],
    },
    clients: {
      title: 'Client List',
      text: 'All your clients in one place. Try clicking a client row to open their full record.',
      actions: [
        { label: 'Click any client row', desc: 'Open their CRM record with timeline and details', clickTarget: 'table tbody tr:first-child, .divide-y > :first-child' },
        { label: 'Try the search bar', desc: 'Filter by name or address' },
      ],
    },
    client_detail: {
      title: 'Client Record',
      text: 'Everything about this client — timeline, activities, ADU details, financials. This is the CRM core.',
      actions: [
        { label: 'Scroll the timeline', desc: 'See every interaction from lead creation to today' },
        { label: 'Check ADU details', desc: 'Property info, budget, and project specs' },
        { label: 'View Estimates', link: '/estimates' },
      ],
    },
    estimates: {
      title: 'Estimates',
      text: 'Detailed construction cost breakdowns. Click an estimate to see line items, markup, and totals.',
      actions: [
        { label: 'Open an estimate', desc: 'Click a row to see the full cost breakdown', clickTarget: 'table tbody tr:first-child, .divide-y a:first-child' },
        { label: 'Check status badges', desc: 'Draft, Sent, Accepted, or Rejected' },
      ],
    },
    estimate_detail: {
      title: 'Estimate Breakdown',
      text: 'Line items by cost code with labor/material splits, waste factors, and auto-calculated totals.',
      actions: [
        { label: 'Review line items', desc: 'Each row shows qty, unit cost, and labor/material %' },
        { label: 'Check the summary', desc: 'Subtotal + overhead + markup + contingency = total' },
        { label: 'View a Schedule', desc: 'See how the project is scheduled', linkFn: 'findScheduleLink' },
      ],
    },
    schedule: {
      title: 'Project Schedule',
      text: 'Tasks organized into phases on a Gantt timeline. Try switching between Gantt, Calendar, and List views.',
      actions: [
        { label: 'Switch views', desc: 'Try Gantt, Calendar, or List tabs', clickTarget: '[data-view], .tabs button, a[href*="view="]' },
        { label: 'Check task statuses', desc: 'Not Started, In Progress, Complete, Blocked' },
        { label: 'See My Tasks', link: '/my-tasks' },
      ],
    },
    my_tasks: {
      title: 'My Tasks',
      text: 'Your personal task view — grouped by today, this week, and overdue. Mobile-optimized.',
      actions: [
        { label: 'Review assignments', desc: 'Tasks assigned to you with priority and dates' },
        { label: 'Check Daily Logs', link: '/daily-logs' },
      ],
    },
    daily_logs: {
      title: 'Daily Logs',
      text: 'Field crews document work performed, crew info, weather, and photos. Logs can be exported as PDFs.',
      actions: [
        { label: 'Open a log', desc: 'Click to see crew details, weather, and work notes', clickTarget: '.space-y-3 > a:first-child' },
        { label: 'View Change Orders', link: '/change-orders' },
      ],
    },
    change_orders: {
      title: 'Change Orders',
      text: 'Track scope changes with line items and cost codes. Approved COs update the budget and contract value.',
      actions: [
        { label: 'Open the demo CO', desc: 'See a quartz countertop upgrade with approval signature', clickTarget: 'table tbody tr:first-child a, .space-y-3 > a:first-child' },
        { label: 'View Payroll', link: '/admin' },
      ],
    },
    my_logs: {
      title: 'Time Tracking',
      text: 'Clock in/out or quick-log hours. Entries are approved by supervisors and flow into payroll.',
      actions: [
        { label: 'Review entries', desc: 'See dates, clients, cost codes, and approval status' },
        { label: 'View Admin Dashboard', link: '/admin' },
      ],
    },
    admin: {
      title: 'Payroll Dashboard',
      text: 'Pending approvals, payroll summaries, and labor cost posting. Approved hours become burdened cost entries.',
      actions: [
        { label: 'Check pending entries', desc: 'Approve or reject time entries' },
        { label: 'View pay period summary', desc: 'Hours, pay, and cost by employee' },
        { label: 'Go to Reports', link: '/reports/channel-spend' },
      ],
    },
    reports: {
      title: 'Channel Spend',
      text: 'Track marketing spend by channel and month. This feeds the ROI calculations.',
      actions: [
        { label: 'Check spend entries', desc: 'See Google Ads spend for this month' },
        { label: 'View ROI Report', link: '/reports/roi' },
      ],
    },
    roi_report: {
      title: 'ROI Report',
      text: 'Cost per lead, cost per deal, and ROI % — broken down by lead source. Export as CSV.',
      actions: [
        { label: 'Review source metrics', desc: 'Leads, deals, spend, and revenue by channel' },
        { label: 'View Settings', link: '/settings/cost-codes' },
      ],
    },
    settings: {
      title: 'Settings',
      text: 'Cost codes, burden multiplier, lead sources, and integrations. Cost codes drive all job costing.',
      actions: [
        { label: 'Review cost codes', desc: 'These appear throughout estimates, budgets, and scheduling' },
        { label: 'Back to Hub', link: '/home' },
      ],
    },
  };

  /* ═══════════════════════ State ═══════════════════════ */

  function getVisited() {
    try {
      return JSON.parse(localStorage.getItem('demoVisited') || '{}');
    } catch { return {}; }
  }
  function markVisited(featureId) {
    var v = getVisited();
    if (!v[featureId]) {
      v[featureId] = true;
      localStorage.setItem('demoVisited', JSON.stringify(v));
      updateProgress();
    }
  }
  function getVisitedCount() {
    return Object.keys(getVisited()).length;
  }

  /* ═══════════════════════ Page Detection ═══════════════════════ */

  function detectCurrentPage() {
    var path = window.location.pathname;
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

  /* ═══════════════════════ Hint Card ═══════════════════════ */

  var hintEl = null;
  var hintDismissed = false;

  function createHintCard(page) {
    var hint = PAGE_HINTS[page];
    if (!hint) return;

    // Don't show if user dismissed on this page
    if (sessionStorage.getItem('demoHintDismissed_' + page)) return;

    hintEl = document.createElement('div');
    hintEl.id = 'demo-hint';
    hintEl.style.cssText =
      'position:fixed;bottom:24px;right:24px;z-index:9990;' +
      'background:white;border-radius:16px;box-shadow:0 8px 40px rgba(0,0,0,0.15);' +
      'padding:20px;max-width:340px;width:calc(100vw - 48px);' +
      'font-family:ui-sans-serif,system-ui,sans-serif;' +
      'animation:demoSlideUp 0.4s cubic-bezier(0.16,1,0.3,1);' +
      'border:1px solid rgba(0,0,0,0.06);';

    var actionsHtml = '';
    if (hint.actions) {
      hint.actions.forEach(function (a) {
        if (a.link) {
          actionsHtml +=
            '<a href="' + a.link + '" class="demo-action-link" style="' +
            'display:flex;align-items:center;gap:8px;padding:8px 12px;' +
            'border-radius:10px;text-decoration:none;color:#0f172a;' +
            'background:#f8fafc;margin-top:6px;transition:background 0.15s;"' +
            ' onmouseenter="this.style.background=\'#f1f5f9\'" onmouseleave="this.style.background=\'#f8fafc\'">' +
            '<svg style="flex-shrink:0;width:16px;height:16px;color:#D6246E" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/></svg>' +
            '<span style="font-size:13px;font-weight:500;">' + a.label + '</span></a>';
        } else if (a.linkFn) {
          var foundLink = findSpecialLink(a.linkFn);
          if (foundLink) {
            actionsHtml +=
              '<a href="' + foundLink + '" class="demo-action-link" style="' +
              'display:flex;align-items:center;gap:8px;padding:8px 12px;' +
              'border-radius:10px;text-decoration:none;color:#0f172a;' +
              'background:#f8fafc;margin-top:6px;transition:background 0.15s;"' +
              ' onmouseenter="this.style.background=\'#f1f5f9\'" onmouseleave="this.style.background=\'#f8fafc\'">' +
              '<svg style="flex-shrink:0;width:16px;height:16px;color:#D6246E" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">' +
              '<path stroke-linecap="round" stroke-linejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3"/></svg>' +
              '<span style="font-size:13px;font-weight:500;">' + a.label + '</span></a>';
          }
        } else {
          actionsHtml +=
            '<div style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;">' +
            '<svg style="flex-shrink:0;width:16px;height:16px;color:#D6246E;margin-top:1px" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">' +
            '<path stroke-linecap="round" stroke-linejoin="round" d="M15.042 21.672L13.684 16.6m0 0l-2.51 2.225.569-9.47 5.227 7.917-3.286-.672zM12 2.25V4.5m5.834.166l-1.591 1.591M20.25 10.5H18M7.757 14.743l-1.59 1.59M6 10.5H3.75m4.007-4.243l-1.59-1.59"/></svg>' +
            '<div>' +
            '<p style="font-size:13px;font-weight:500;color:#0f172a;margin:0;">' + a.label + '</p>' +
            (a.desc ? '<p style="font-size:12px;color:#64748b;margin:2px 0 0;">' + a.desc + '</p>' : '') +
            '</div></div>';
        }
      });
    }

    var visited = getVisited();
    var visitedCount = getVisitedCount();
    var total = FEATURES.length;

    hintEl.innerHTML =
      '<div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px;">' +
        '<div style="display:flex;align-items:center;gap:6px;">' +
          '<div style="width:28px;height:28px;border-radius:8px;background:linear-gradient(135deg,#D6246E,#e84393);display:flex;align-items:center;justify-content:center;">' +
            '<svg style="width:14px;height:14px;color:white" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z"/></svg>' +
          '</div>' +
          '<span style="font-size:11px;font-weight:600;color:#D6246E;text-transform:uppercase;letter-spacing:0.05em;">Try it out</span>' +
        '</div>' +
        '<button id="demo-hint-close" style="background:none;border:none;cursor:pointer;padding:4px;color:#94a3b8;font-size:18px;line-height:1;" title="Dismiss">&times;</button>' +
      '</div>' +
      '<h3 style="font-size:16px;font-weight:700;color:#0f172a;margin:0 0 4px;">' + hint.title + '</h3>' +
      '<p style="font-size:13px;color:#475569;margin:0 0 12px;line-height:1.5;">' + hint.text + '</p>' +
      '<div style="border-top:1px solid #f1f5f9;padding-top:10px;">' + actionsHtml + '</div>' +
      (visitedCount >= total ? '<div style="margin-top:12px;padding:10px 12px;border-radius:10px;background:linear-gradient(135deg,#f0fdf4,#ecfdf5);text-align:center;">' +
        '<p style="font-size:13px;font-weight:600;color:#16a34a;margin:0;">You\'ve explored everything!</p>' +
        '<a href="/demo/exit" style="display:inline-block;margin-top:6px;font-size:12px;color:#16a34a;text-decoration:underline;">Exit demo &amp; remove sample data</a>' +
      '</div>' : '');

    document.body.appendChild(hintEl);

    // Attach highlight behavior
    if (hint.actions) {
      hint.actions.forEach(function (a) {
        if (a.clickTarget) {
          var target = document.querySelector(a.clickTarget);
          if (target) {
            target.style.outline = '2px dashed #D6246E';
            target.style.outlineOffset = '2px';
            target.style.borderRadius = '8px';
            target.dataset.demoHighlight = '1';
          }
        }
      });
    }

    // Close handler
    var closeBtn = document.getElementById('demo-hint-close');
    if (closeBtn) {
      closeBtn.addEventListener('click', function () {
        sessionStorage.setItem('demoHintDismissed_' + page, '1');
        if (hintEl) hintEl.remove();
        hintEl = null;
        // Remove highlights
        document.querySelectorAll('[data-demo-highlight]').forEach(function (el) {
          el.style.outline = '';
          el.style.outlineOffset = '';
        });
      });
    }
  }

  function findSpecialLink(fnName) {
    if (fnName === 'findScheduleLink') {
      var link = document.querySelector('a[href*="/schedule/"]');
      return link ? link.getAttribute('href') : null;
    }
    return null;
  }

  /* ═══════════════════════ Checklist Panel ═══════════════════════ */

  var checklistEl = null;
  var checklistOpen = false;

  function createChecklistPanel() {
    checklistEl = document.createElement('div');
    checklistEl.id = 'demo-checklist';
    checklistEl.style.cssText =
      'position:fixed;top:44px;right:0;z-index:9995;' +
      'background:white;border-radius:0 0 0 16px;box-shadow:-4px 4px 24px rgba(0,0,0,0.12);' +
      'width:280px;max-height:calc(100vh - 60px);overflow-y:auto;' +
      'font-family:ui-sans-serif,system-ui,sans-serif;' +
      'transform:translateX(100%);transition:transform 0.3s cubic-bezier(0.16,1,0.3,1);' +
      'border-left:1px solid rgba(0,0,0,0.06);border-bottom:1px solid rgba(0,0,0,0.06);';

    renderChecklist();
    document.body.appendChild(checklistEl);
  }

  function renderChecklist() {
    if (!checklistEl) return;
    var visited = getVisited();
    var visitedCount = getVisitedCount();
    var total = FEATURES.length;
    var pct = Math.round((visitedCount / total) * 100);

    var itemsHtml = '';
    FEATURES.forEach(function (f) {
      var done = visited[f.id];
      var isCurrent = (f.page === detectCurrentPage());
      itemsHtml +=
        '<div style="display:flex;align-items:center;gap:10px;padding:8px 16px;' +
        (isCurrent ? 'background:#fdf2f8;' : '') +
        'cursor:' + (f.path ? 'pointer' : 'default') + ';" ' +
        (f.path ? 'onclick="window.location.href=\'' + f.path + '\'"' : '') +
        ' class="demo-checklist-item">' +
          '<div style="width:20px;height:20px;border-radius:6px;flex-shrink:0;display:flex;align-items:center;justify-content:center;' +
          (done
            ? 'background:#D6246E;'
            : 'border:2px solid ' + (isCurrent ? '#D6246E' : '#e2e8f0') + ';background:transparent;') +
          '">' +
            (done ? '<svg style="width:12px;height:12px;color:white" fill="none" stroke="currentColor" stroke-width="3" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4.5 12.75l6 6 9-13.5"/></svg>' : '') +
          '</div>' +
          '<span style="font-size:13px;' +
          (done ? 'color:#94a3b8;text-decoration:line-through;' : (isCurrent ? 'color:#D6246E;font-weight:600;' : 'color:#334155;font-weight:500;')) +
          '">' + f.label + '</span>' +
        '</div>';
    });

    checklistEl.innerHTML =
      '<div style="padding:16px;border-bottom:1px solid #f1f5f9;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">' +
          '<h3 style="font-size:14px;font-weight:700;color:#0f172a;margin:0;">Explore the app</h3>' +
          '<span style="font-size:12px;font-weight:600;color:#D6246E;">' + visitedCount + '/' + total + '</span>' +
        '</div>' +
        '<div style="height:4px;background:#f1f5f9;border-radius:2px;overflow:hidden;">' +
          '<div style="height:100%;width:' + pct + '%;background:linear-gradient(90deg,#D6246E,#e84393);border-radius:2px;transition:width 0.5s cubic-bezier(0.16,1,0.3,1);"></div>' +
        '</div>' +
      '</div>' +
      '<div style="padding:8px 0;">' + itemsHtml + '</div>' +
      (visitedCount >= total
        ? '<div style="padding:12px 16px;border-top:1px solid #f1f5f9;text-align:center;">' +
            '<p style="font-size:13px;font-weight:600;color:#16a34a;margin:0 0 6px;">All done!</p>' +
            '<a href="/demo/exit" style="display:inline-block;padding:8px 20px;border-radius:8px;background:#0f172a;color:white;font-size:13px;font-weight:600;text-decoration:none;">Exit Demo</a>' +
          '</div>'
        : '');
  }

  function toggleChecklist() {
    checklistOpen = !checklistOpen;
    if (checklistEl) {
      checklistEl.style.transform = checklistOpen ? 'translateX(0)' : 'translateX(100%)';
    }
  }

  /* ═══════════════════════ Progress ═══════════════════════ */

  function updateProgress() {
    var label = document.getElementById('demo-progress-label');
    if (label) {
      label.textContent = getVisitedCount() + '/' + FEATURES.length;
    }
    renderChecklist();
  }

  /* ═══════════════════════ Init ═══════════════════════ */

  function init() {
    if (!document.getElementById('demo-banner')) return;

    // Inject animation CSS
    var style = document.createElement('style');
    style.textContent =
      '@keyframes demoSlideUp{from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)}}' +
      '.demo-checklist-item:hover{background:#fdf2f8 !important}' +
      '#demo-hint a.demo-action-link:hover{background:#f1f5f9 !important}';
    document.head.appendChild(style);

    var currentPage = detectCurrentPage();

    // Mark current page as visited
    if (currentPage) {
      var feature = FEATURES.find(function (f) { return f.page === currentPage; });
      if (feature) markVisited(feature.id);
    }

    // Update progress counter
    updateProgress();

    // Create checklist panel
    createChecklistPanel();

    // Bind checklist toggle button
    var toggleBtn = document.getElementById('demo-checklist-toggle');
    if (toggleBtn) {
      toggleBtn.addEventListener('click', toggleChecklist);
    }

    // Show page hint (with a slight delay for the page to settle)
    if (currentPage) {
      setTimeout(function () { createHintCard(currentPage); }, 500);
    }

    // Close checklist when clicking outside
    document.addEventListener('click', function (e) {
      if (checklistOpen && checklistEl && !checklistEl.contains(e.target)) {
        var toggleBtn = document.getElementById('demo-checklist-toggle');
        if (toggleBtn && !toggleBtn.contains(e.target)) {
          toggleChecklist();
        }
      }
    });
  }

  // Run when DOM is ready
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

})();
