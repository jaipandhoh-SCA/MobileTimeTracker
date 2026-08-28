/**
 * field-status.js — Sync status indicator and flow instrumentation.
 *
 * Provides:
 * 1. Alpine.js component `syncStatus()` for the nav-bar indicator
 * 2. `FieldInstrumentation` — lightweight tap/time tracking per entry flow
 *
 * Design rules:
 * - Synced = invisible. No green check, no badge, nothing.
 * - Pending = subtle count, tappable to expand.
 * - Failed = count turns red, one-tap retry in the list.
 * - Never a blocking spinner. Never a celebration.
 */

// ═══════════════════════════════════════════════════════════════════════
// 1. SYNC STATUS — Alpine.js component
// ═══════════════════════════════════════════════════════════════════════

function syncStatus() {
  return {
    pending: 0,
    syncing: 0,
    failed: 0,
    total: 0,
    mediaPending: 0,
    online: navigator.onLine,
    open: false,
    entries: [],

    init() {
      // Subscribe to queue changes
      if (window.FieldQueue) {
        window.FieldQueue.subscribe((status) => {
          this.pending = status.pending;
          this.syncing = status.syncing;
          this.failed = status.failed;
          this.total = status.total;
          this.mediaPending = status.mediaPending;

          // Auto-refresh detail list when panel is open
          if (this.open) this._loadEntries();
        });
      }

      window.addEventListener('online', () => { this.online = true; });
      window.addEventListener('offline', () => { this.online = false; });
    },

    // Is the indicator visible at all?
    get visible() {
      return this.total > 0 || !this.online;
    },

    // Badge count (pending + failed)
    get badgeCount() {
      return this.pending + this.failed;
    },

    // Badge color class
    get badgeClass() {
      if (this.failed > 0) return 'bg-neg text-white';
      if (!this.online) return 'bg-amber-500 text-white';
      return 'bg-txt-secondary text-white';
    },

    // Indicator icon state
    get iconState() {
      if (this.failed > 0) return 'failed';
      if (!this.online) return 'offline';
      if (this.syncing > 0) return 'syncing';
      if (this.pending > 0) return 'pending';
      return 'idle';
    },

    toggle() {
      this.open = !this.open;
      if (this.open) this._loadEntries();
    },

    async _loadEntries() {
      if (!window.FieldQueue) return;
      const all = await window.FieldQueue.getEntries();
      // Show non-synced entries, plus recently synced (last 5 min)
      const cutoff = new Date(Date.now() - 300000).toISOString();
      this.entries = all
        .filter(e => e.status !== 'synced' || e.updatedAt > cutoff)
        .sort((a, b) => {
          // Failed first, then pending, then syncing, then synced
          const order = { failed: 0, pending: 1, syncing: 2, synced: 3 };
          const diff = (order[a.status] || 9) - (order[b.status] || 9);
          if (diff !== 0) return diff;
          return b.createdAt.localeCompare(a.createdAt);
        })
        .slice(0, 50);
    },

    // Format entry type for display
    typeLabel(type) {
      const labels = {
        daily_log: 'Daily log',
        time_punch: 'Time punch',
        material_note: 'Material',
        general_note: 'Note',
      };
      return labels[type] || type;
    },

    // Format relative time
    timeAgo(isoStr) {
      const ms = Date.now() - new Date(isoStr).getTime();
      if (ms < 60000) return 'just now';
      if (ms < 3600000) return Math.floor(ms / 60000) + 'm ago';
      if (ms < 86400000) return Math.floor(ms / 3600000) + 'h ago';
      return Math.floor(ms / 86400000) + 'd ago';
    },

    // Status label for display
    statusLabel(status) {
      return {
        pending: 'Waiting',
        syncing: 'Syncing',
        synced: 'Synced',
        failed: 'Failed',
      }[status] || status;
    },

    // Status color
    statusClass(status) {
      return {
        pending: 'text-txt-secondary',
        syncing: 'text-txt-secondary',
        synced: 'text-pos',
        failed: 'text-neg',
      }[status] || 'text-txt-muted';
    },

    // Retry a single failed entry
    async retryEntry(clientUuid) {
      if (!window.FieldQueue) return;
      await window.FieldQueue.updateStatus(clientUuid, 'pending', null);
      if (window.FieldSync && this.online) {
        window.FieldSync.syncNow();
      }
      await this._loadEntries();
    },

    // Retry all failed entries
    async retryAll() {
      if (!window.FieldQueue) return;
      const failed = await window.FieldQueue.getEntries({ status: 'failed' });
      for (const entry of failed) {
        await window.FieldQueue.updateStatus(entry.clientUuid, 'pending', null);
      }
      if (window.FieldSync && this.online) {
        window.FieldSync.syncNow();
      }
      await this._loadEntries();
    },

    // Force sync now
    syncNow() {
      if (window.FieldSync && this.online) {
        window.FieldSync.syncNow();
      }
    },
  };
}


// ═══════════════════════════════════════════════════════════════════════
// 2. FLOW INSTRUMENTATION
// ═══════════════════════════════════════════════════════════════════════
//
// Tracks taps-to-complete and time-to-complete for each entry flow.
// Data is stored in localStorage and can be read by analytics or tests.
//
// Usage:
//   FieldInstrumentation.start('daily_log');    // user opens a form
//   FieldInstrumentation.tap('daily_log');       // each tap/interaction
//   FieldInstrumentation.complete('daily_log');  // user saves
//
// Recorded data (per completed flow):
//   { type, taps, durationMs, completedAt }

const FieldInstrumentation = {

  _STORAGE_KEY: 'field_flow_metrics',
  _MAX_ENTRIES: 200,
  _active: {},

  /**
   * Start tracking a new flow.
   * @param {string} flowType — e.g. 'daily_log', 'time_punch'
   * @returns {string} flowId for this tracking session
   */
  start(flowType) {
    const flowId = flowType + '_' + Date.now();
    this._active[flowId] = {
      type: flowType,
      startedAt: Date.now(),
      taps: 0,
    };
    return flowId;
  },

  /**
   * Record a tap/interaction in the active flow.
   * If no flowId given, increments the most recent flow of that type.
   */
  tap(flowIdOrType) {
    const flow = this._resolve(flowIdOrType);
    if (flow) flow.taps++;
  },

  /**
   * Mark a flow as complete. Records the metric to localStorage.
   */
  complete(flowIdOrType) {
    const key = this._resolveKey(flowIdOrType);
    const flow = key ? this._active[key] : null;
    if (!flow) return null;

    const metric = {
      type: flow.type,
      taps: flow.taps,
      durationMs: Date.now() - flow.startedAt,
      completedAt: new Date().toISOString(),
    };

    this._store(metric);
    delete this._active[key];
    return metric;
  },

  /**
   * Abandon a flow without recording (e.g. user navigated away).
   */
  abandon(flowIdOrType) {
    const key = this._resolveKey(flowIdOrType);
    if (key) delete this._active[key];
  },

  /**
   * Get all recorded metrics, optionally filtered by type.
   */
  getMetrics(type) {
    const all = this._load();
    return type ? all.filter(m => m.type === type) : all;
  },

  /**
   * Get summary stats for a flow type.
   * @returns {{ count, avgTaps, avgDurationMs, p50DurationMs, p90DurationMs }}
   */
  getSummary(type) {
    const metrics = this.getMetrics(type);
    if (!metrics.length) return null;

    const taps = metrics.map(m => m.taps);
    const durations = metrics.map(m => m.durationMs).sort((a, b) => a - b);

    return {
      count: metrics.length,
      avgTaps: Math.round(taps.reduce((a, b) => a + b, 0) / taps.length * 10) / 10,
      avgDurationMs: Math.round(durations.reduce((a, b) => a + b, 0) / durations.length),
      p50DurationMs: durations[Math.floor(durations.length * 0.5)],
      p90DurationMs: durations[Math.floor(durations.length * 0.9)],
    };
  },

  /** Clear all stored metrics. */
  clear() {
    localStorage.removeItem(this._STORAGE_KEY);
  },

  // ── Internal ──────────────────────────────────────────────────────

  _resolve(idOrType) {
    if (this._active[idOrType]) return this._active[idOrType];
    // Find most recent active flow of this type
    const key = this._resolveKey(idOrType);
    return key ? this._active[key] : null;
  },

  _resolveKey(idOrType) {
    if (this._active[idOrType]) return idOrType;
    // Find most recent active flow matching the type prefix
    const keys = Object.keys(this._active)
      .filter(k => k.startsWith(idOrType + '_'))
      .sort()
      .reverse();
    return keys[0] || null;
  },

  _load() {
    try {
      return JSON.parse(localStorage.getItem(this._STORAGE_KEY) || '[]');
    } catch { return []; }
  },

  _store(metric) {
    const all = this._load();
    all.push(metric);
    // Trim to max entries
    while (all.length > this._MAX_ENTRIES) all.shift();
    localStorage.setItem(this._STORAGE_KEY, JSON.stringify(all));
  },
};

// Export
if (typeof window !== 'undefined') {
  window.syncStatus = syncStatus;
  window.FieldInstrumentation = FieldInstrumentation;
}
