/**
 * field-queue.js — Offline-first local write queue for field data capture.
 *
 * Storage: IndexedDB ("adu-field-queue", v1).
 * Why IndexedDB:
 *   - Survives app termination, OS kills, and browser restart (requirement 7)
 *   - Stores binary blobs for photos/audio without base64 overhead
 *   - No 5-10MB cap like localStorage (typically 50-500MB+)
 *   - Async API doesn't block the UI thread
 *   - Available in service workers for background sync
 *
 * ── Conflict policy ──────────────────────────────────────────────────────
 * LAST-WRITE-WINS per record for all types EXCEPT time punches.
 *
 * - daily_log, material_note, general_note:
 *   If server has a record with the same client_uuid, it overwrites with the
 *   newer payload. The client always sends the full record; the server does
 *   an upsert keyed on client_uuid. Last POST wins.
 *
 * - time_punch:
 *   APPEND-ONLY. The server never overwrites an existing time punch with the
 *   same client_uuid — it returns status:"duplicate" and the client marks
 *   the entry as synced. This prevents clock-in/out records from being
 *   mutated after capture, which is a payroll integrity requirement.
 *
 * - photo, audio:
 *   Uploaded separately from their parent record. A photo references its
 *   parent entry's client_uuid. Photos never block text record syncing.
 *   If a photo upload fails, the text record still syncs; the photo stays
 *   queued and retries independently.
 * ─────────────────────────────────────────────────────────────────────────
 */

const DB_NAME = 'adu-field-queue';
const DB_VERSION = 2; // v2 adds media store
const ENTRIES_STORE = 'entries';
const MEDIA_STORE = 'media';

// ── Entry statuses ──────────────────────────────────────────────────────
const STATUS = Object.freeze({
  PENDING:  'pending',
  SYNCING:  'syncing',
  SYNCED:   'synced',
  FAILED:   'failed',
});

// ── Entry types ─────────────────────────────────────────────────────────
const ENTRY_TYPE = Object.freeze({
  DAILY_LOG:   'daily_log',
  TIME_PUNCH:  'time_punch',
  CLOCK_IN:    'clock_in',
  CLOCK_OUT:   'clock_out',
  MATERIAL:    'material_note',
  NOTE:        'general_note',
});

// ── Database handle (singleton) ─────────────────────────────────────────
let _dbPromise = null;

function _openDB() {
  if (_dbPromise) return _dbPromise;
  _dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);

    req.onupgradeneeded = (e) => {
      const db = e.target.result;

      // Entries store: text records (logs, punches, notes)
      if (!db.objectStoreNames.contains(ENTRIES_STORE)) {
        const store = db.createObjectStore(ENTRIES_STORE, { keyPath: 'clientUuid' });
        store.createIndex('status', 'status', { unique: false });
        store.createIndex('type', 'type', { unique: false });
        store.createIndex('createdAt', 'createdAt', { unique: false });
      }

      // Media store: photos and audio blobs
      if (!db.objectStoreNames.contains(MEDIA_STORE)) {
        const mstore = db.createObjectStore(MEDIA_STORE, { keyPath: 'mediaUuid' });
        mstore.createIndex('parentUuid', 'parentUuid', { unique: false });
        mstore.createIndex('status', 'status', { unique: false });
      }
    };

    req.onsuccess = () => resolve(req.result);
    req.onerror = () => {
      _dbPromise = null;
      reject(req.error);
    };
  });
  return _dbPromise;
}

// ── UUID generator ──────────────────────────────────────────────────────
function _uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// ── IDB transaction helpers ─────────────────────────────────────────────
function _tx(storeName, mode) {
  return _openDB().then((db) => {
    const tx = db.transaction(storeName, mode);
    return tx.objectStore(storeName);
  });
}

function _put(storeName, record) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readwrite');
      const store = tx.objectStore(storeName);
      const req = store.put(record);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  });
}

function _get(storeName, key) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const req = tx.objectStore(storeName).get(key);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  });
}

function _delete(storeName, key) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readwrite');
      const req = tx.objectStore(storeName).delete(key);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error);
    });
  });
}

function _getAll(storeName) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const req = tx.objectStore(storeName).getAll();
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  });
}

function _getAllByIndex(storeName, indexName, value) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const idx = tx.objectStore(storeName).index(indexName);
      const req = idx.getAll(value);
      req.onsuccess = () => resolve(req.result || []);
      req.onerror = () => reject(req.error);
    });
  });
}

function _countByIndex(storeName, indexName, value) {
  return _openDB().then((db) => {
    return new Promise((resolve, reject) => {
      const tx = db.transaction(storeName, 'readonly');
      const idx = tx.objectStore(storeName).index(indexName);
      const req = idx.count(value);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  });
}

// ═════════════════════════════════════════════════════════════════════════
// PUBLIC API — FieldQueue
// ═════════════════════════════════════════════════════════════════════════

const FieldQueue = {

  STATUS,
  ENTRY_TYPE,

  /**
   * Write an entry to the local queue. Returns immediately.
   * The entry is persisted to IndexedDB before this resolves.
   *
   * @param {string} type — One of ENTRY_TYPE values
   * @param {object} data — The entry payload (all form fields)
   * @param {object} [options]
   * @param {string} [options.clientUuid] — Override UUID (for edits)
   * @returns {Promise<{clientUuid: string, status: string}>}
   */
  async enqueue(type, data, options = {}) {
    const clientUuid = options.clientUuid || _uuid();
    const now = new Date().toISOString();

    const record = {
      clientUuid,
      type,
      status: STATUS.PENDING,
      data,
      createdAt: now,
      updatedAt: now,
      retryCount: 0,
      lastError: null,
    };

    await _put(ENTRIES_STORE, record);
    this._notifyListeners();
    return { clientUuid, status: STATUS.PENDING };
  },

  /**
   * Queue a photo or audio file linked to a parent entry.
   * The blob is stored in IndexedDB; the parent entry syncs independently.
   *
   * @param {string} parentUuid — clientUuid of the parent entry
   * @param {File|Blob} blob — The image/audio file
   * @param {object} [meta] — Caption, cost_code_id, etc.
   * @returns {Promise<{mediaUuid: string, status: string}>}
   */
  async enqueueMedia(parentUuid, blob, meta = {}) {
    const mediaUuid = _uuid();
    const now = new Date().toISOString();

    const record = {
      mediaUuid,
      parentUuid,
      status: STATUS.PENDING,
      blob,
      fileName: blob.name || `photo_${Date.now()}.jpg`,
      mimeType: blob.type || 'image/jpeg',
      meta,
      createdAt: now,
      retryCount: 0,
      lastError: null,
    };

    await _put(MEDIA_STORE, record);
    this._notifyListeners();
    return { mediaUuid, status: STATUS.PENDING };
  },

  /**
   * Get all entries, optionally filtered by status and/or type.
   */
  async getEntries(filters = {}) {
    let entries;
    if (filters.status) {
      entries = await _getAllByIndex(ENTRIES_STORE, 'status', filters.status);
    } else {
      entries = await _getAll(ENTRIES_STORE);
    }
    if (filters.type) {
      entries = entries.filter((e) => e.type === filters.type);
    }
    return entries.sort((a, b) => a.createdAt.localeCompare(b.createdAt));
  },

  /**
   * Get all media for a parent entry.
   */
  async getMediaForEntry(parentUuid) {
    return _getAllByIndex(MEDIA_STORE, 'parentUuid', parentUuid);
  },

  /**
   * Get a single entry by its clientUuid.
   */
  async getEntry(clientUuid) {
    return _get(ENTRIES_STORE, clientUuid);
  },

  /**
   * Update an entry's status (used by the sync worker).
   */
  async updateStatus(clientUuid, status, error = null) {
    const entry = await _get(ENTRIES_STORE, clientUuid);
    if (!entry) return;
    entry.status = status;
    entry.updatedAt = new Date().toISOString();
    if (error) entry.lastError = error;
    if (status === STATUS.SYNCING) entry.retryCount = (entry.retryCount || 0) + 1;
    await _put(ENTRIES_STORE, entry);
    this._notifyListeners();
  },

  /**
   * Update a media item's status.
   */
  async updateMediaStatus(mediaUuid, status, error = null) {
    const item = await _get(MEDIA_STORE, mediaUuid);
    if (!item) return;
    item.status = status;
    if (error) item.lastError = error;
    if (status === STATUS.SYNCING) item.retryCount = (item.retryCount || 0) + 1;
    await _put(MEDIA_STORE, item);
    this._notifyListeners();
  },

  /**
   * Remove a synced entry from the queue (cleanup).
   */
  async remove(clientUuid) {
    await _delete(ENTRIES_STORE, clientUuid);
    // Also remove associated media
    const media = await _getAllByIndex(MEDIA_STORE, 'parentUuid', clientUuid);
    for (const m of media) {
      await _delete(MEDIA_STORE, m.mediaUuid);
    }
    this._notifyListeners();
  },

  /**
   * Remove a single media item.
   */
  async removeMedia(mediaUuid) {
    await _delete(MEDIA_STORE, mediaUuid);
    this._notifyListeners();
  },

  // ── Sync status model ───────────────────────────────────────────────
  // UI subscribes to this for reactive "N items waiting" counts.

  /**
   * Get current sync status counts.
   * @returns {Promise<{pending: number, syncing: number, failed: number, synced: number, total: number, mediaPending: number}>}
   */
  async getStatus() {
    const [pending, syncing, failed, synced, mediaPending] = await Promise.all([
      _countByIndex(ENTRIES_STORE, 'status', STATUS.PENDING),
      _countByIndex(ENTRIES_STORE, 'status', STATUS.SYNCING),
      _countByIndex(ENTRIES_STORE, 'status', STATUS.FAILED),
      _countByIndex(ENTRIES_STORE, 'status', STATUS.SYNCED),
      _countByIndex(MEDIA_STORE, 'status', STATUS.PENDING),
    ]);
    return {
      pending,
      syncing,
      failed,
      synced,
      total: pending + syncing + failed,
      mediaPending,
    };
  },

  /**
   * Purge all synced entries older than the given age (ms).
   * Defaults to 24 hours.
   */
  async purgeSynced(maxAgeMs = 86400000) {
    const entries = await _getAllByIndex(ENTRIES_STORE, 'status', STATUS.SYNCED);
    const cutoff = new Date(Date.now() - maxAgeMs).toISOString();
    for (const e of entries) {
      if (e.updatedAt < cutoff) {
        await this.remove(e.clientUuid);
      }
    }
  },

  // ── Listener management ─────────────────────────────────────────────
  // Simple pub/sub so UI components can react to queue changes.

  _listeners: [],

  /**
   * Subscribe to queue changes. Callback receives the status object.
   * Returns an unsubscribe function.
   */
  subscribe(callback) {
    this._listeners.push(callback);
    // Immediately fire with current status
    this.getStatus().then(callback);
    return () => {
      this._listeners = this._listeners.filter((cb) => cb !== callback);
    };
  },

  _notifyListeners() {
    this.getStatus().then((status) => {
      for (const cb of this._listeners) {
        try { cb(status); } catch (e) { /* don't break other listeners */ }
      }
    });
  },
};

// Make available globally and as ES module
if (typeof window !== 'undefined') {
  window.FieldQueue = FieldQueue;
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { FieldQueue, STATUS, ENTRY_TYPE };
}
