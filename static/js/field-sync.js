/**
 * field-sync.js — Background sync worker for the field data queue.
 *
 * Drains FieldQueue entries when online. Handles:
 * - Exponential backoff with jitter (1s → 2s → 4s → ... → 5min cap)
 * - Max 20 retries per entry before marking FAILED
 * - Text records sync before and independently from media
 * - Photos/audio upload separately so a large file never blocks a time punch
 * - Duplicate detection: server returns status:"duplicate" → mark synced
 * - Connectivity-aware: pauses when offline, resumes on reconnect
 *
 * ── Conflict policy (enforced server-side, documented here) ──────────
 * - time_punch: APPEND-ONLY. Server rejects updates to existing UUID.
 * - All other types: LAST-WRITE-WINS. Server upserts on client_uuid.
 * ─────────────────────────────────────────────────────────────────────
 */

(function () {
  'use strict';

  // ── Config ──────────────────────────────────────────────────────────
  const SYNC_ENDPOINT = '/api/field/sync';
  const MEDIA_ENDPOINT = '/api/field/media';
  const INITIAL_BACKOFF_MS = 1000;
  const MAX_BACKOFF_MS = 300000; // 5 minutes
  const MAX_RETRIES = 20;
  const POLL_INTERVAL_MS = 5000; // check queue every 5s when online
  const BATCH_SIZE = 10; // max entries per sync cycle

  // ── State ───────────────────────────────────────────────────────────
  let _running = false;
  let _timer = null;
  let _currentBackoff = INITIAL_BACKOFF_MS;

  // ── Backoff calculation ─────────────────────────────────────────────
  function _nextBackoff(current) {
    // Exponential with ±25% jitter, capped
    const doubled = Math.min(current * 2, MAX_BACKOFF_MS);
    const jitter = doubled * (0.75 + Math.random() * 0.5);
    return Math.round(jitter);
  }

  function _resetBackoff() {
    _currentBackoff = INITIAL_BACKOFF_MS;
  }

  // ── CSRF token ──────────────────────────────────────────────────────
  function _getCSRF() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    if (meta) return meta.content;
    const input = document.querySelector('input[name="csrf_token"]');
    if (input) return input.value;
    return '';
  }

  // ── Sync one text entry ─────────────────────────────────────────────
  async function _syncEntry(entry) {
    const FQ = window.FieldQueue;
    if (!FQ) return false;

    // Skip if max retries exceeded
    if ((entry.retryCount || 0) >= MAX_RETRIES) {
      await FQ.updateStatus(entry.clientUuid, FQ.STATUS.FAILED,
        `Max retries (${MAX_RETRIES}) exceeded`);
      return false;
    }

    await FQ.updateStatus(entry.clientUuid, FQ.STATUS.SYNCING);

    try {
      const resp = await fetch(SYNC_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': _getCSRF(),
        },
        body: JSON.stringify({
          client_uuid: entry.clientUuid,
          type: entry.type,
          data: entry.data,
          created_at: entry.createdAt,
          updated_at: entry.updatedAt,
        }),
      });

      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text.substring(0, 200)}`);
      }

      const result = await resp.json();

      if (result.ok) {
        // "created", "updated", or "duplicate" all mean we're done
        await FQ.updateStatus(entry.clientUuid, FQ.STATUS.SYNCED);
        _resetBackoff();
        return true;
      } else {
        throw new Error(result.error || 'Server returned ok:false');
      }
    } catch (err) {
      await FQ.updateStatus(entry.clientUuid, FQ.STATUS.PENDING,
        err.message || 'Sync failed');
      return false;
    }
  }

  // ── Sync one media item ─────────────────────────────────────────────
  async function _syncMedia(item) {
    const FQ = window.FieldQueue;
    if (!FQ) return false;

    if ((item.retryCount || 0) >= MAX_RETRIES) {
      await FQ.updateMediaStatus(item.mediaUuid, FQ.STATUS.FAILED,
        `Max retries (${MAX_RETRIES}) exceeded`);
      return false;
    }

    // Only upload media if the parent entry has synced
    const parent = await FQ.getEntry(item.parentUuid);
    if (parent && parent.status !== FQ.STATUS.SYNCED) {
      // Parent hasn't synced yet — skip media for now
      return false;
    }

    await FQ.updateMediaStatus(item.mediaUuid, FQ.STATUS.SYNCING);

    try {
      const fd = new FormData();
      fd.append('media_uuid', item.mediaUuid);
      fd.append('parent_uuid', item.parentUuid);
      fd.append('file', item.blob, item.fileName);
      fd.append('mime_type', item.mimeType);
      if (item.meta) {
        fd.append('meta', JSON.stringify(item.meta));
      }

      const resp = await fetch(MEDIA_ENDPOINT, {
        method: 'POST',
        headers: { 'X-CSRFToken': _getCSRF() },
        body: fd,
      });

      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status}: ${text.substring(0, 200)}`);
      }

      const result = await resp.json();
      if (result.ok) {
        await FQ.updateMediaStatus(item.mediaUuid, FQ.STATUS.SYNCED);
        _resetBackoff();
        return true;
      } else {
        throw new Error(result.error || 'Media upload failed');
      }
    } catch (err) {
      await FQ.updateMediaStatus(item.mediaUuid, FQ.STATUS.PENDING,
        err.message || 'Media sync failed');
      return false;
    }
  }

  // ── Main sync cycle ─────────────────────────────────────────────────
  async function _syncCycle() {
    const FQ = window.FieldQueue;
    if (!FQ || !navigator.onLine) return;

    // 1. Sync pending text entries (oldest first, batch limited)
    const pending = await FQ.getEntries({ status: FQ.STATUS.PENDING });
    let synced = 0;
    let failed = 0;

    for (const entry of pending.slice(0, BATCH_SIZE)) {
      const ok = await _syncEntry(entry);
      if (ok) {
        synced++;
      } else {
        failed++;
        // If a non-retryable failure, continue to next entry
        // If a network failure, stop the cycle
        if (!navigator.onLine) break;
      }
    }

    // 2. Sync pending media (only for entries already synced)
    const mediaItems = await FQ.getEntries({ status: FQ.STATUS.SYNCED });
    // Get synced entry UUIDs
    const syncedUuids = new Set(mediaItems.map((e) => e.clientUuid));

    const allMedia = await _getAllPendingMedia();
    for (const item of allMedia.slice(0, BATCH_SIZE)) {
      // Only sync media whose parent is synced (or parent is gone = orphan cleanup)
      const parent = await FQ.getEntry(item.parentUuid);
      if (!parent) {
        // Orphaned media — parent was removed. Clean up.
        await FQ.removeMedia(item.mediaUuid);
        continue;
      }
      if (parent.status === FQ.STATUS.SYNCED) {
        await _syncMedia(item);
        if (!navigator.onLine) break;
      }
    }

    // 3. Purge old synced entries
    await FQ.purgeSynced();

    // 4. Schedule next cycle
    if (synced > 0 && (await FQ.getStatus()).pending > 0) {
      // More to sync — go again quickly
      _scheduleSync(POLL_INTERVAL_MS);
    } else if (failed > 0) {
      // Back off on failures
      _scheduleSync(_currentBackoff);
      _currentBackoff = _nextBackoff(_currentBackoff);
    } else {
      // Idle — poll at normal interval
      _scheduleSync(POLL_INTERVAL_MS);
    }
  }

  async function _getAllPendingMedia() {
    const FQ = window.FieldQueue;
    if (!FQ) return [];
    // Access IndexedDB directly for media store
    try {
      const db = await new Promise((resolve, reject) => {
        const req = indexedDB.open('adu-field-queue');
        req.onsuccess = () => resolve(req.result);
        req.onerror = () => reject(req.error);
      });
      return new Promise((resolve, reject) => {
        const tx = db.transaction('media', 'readonly');
        const idx = tx.objectStore('media').index('status');
        const req = idx.getAll('pending');
        req.onsuccess = () => resolve(req.result || []);
        req.onerror = () => reject(req.error);
      });
    } catch (e) {
      return [];
    }
  }

  // ── Scheduling ──────────────────────────────────────────────────────
  function _scheduleSync(delayMs) {
    if (_timer) clearTimeout(_timer);
    _timer = setTimeout(() => {
      if (_running) return; // prevent overlapping cycles
      _running = true;
      _syncCycle()
        .catch((e) => console.warn('[FieldSync] cycle error:', e))
        .finally(() => { _running = false; });
    }, delayMs);
  }

  // ── Start / stop ───────────────────────────────────────────────────
  function start() {
    // Start syncing
    _scheduleSync(1000); // first check after 1s

    // Listen for connectivity changes
    window.addEventListener('online', () => {
      _resetBackoff();
      _scheduleSync(500); // sync quickly when coming back online
    });

    window.addEventListener('offline', () => {
      if (_timer) clearTimeout(_timer);
    });

    // Also sync when page becomes visible (user switches back to app)
    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState === 'visible' && navigator.onLine) {
        _scheduleSync(1000);
      }
    });
  }

  function stop() {
    if (_timer) clearTimeout(_timer);
    _timer = null;
  }

  // ── Public API ──────────────────────────────────────────────────────
  const FieldSync = {
    start,
    stop,
    /** Force an immediate sync cycle */
    async syncNow() {
      if (_running) return;
      _running = true;
      try {
        await _syncCycle();
      } finally {
        _running = false;
      }
    },
  };

  if (typeof window !== 'undefined') {
    window.FieldSync = FieldSync;
  }
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { FieldSync };
  }
})();
