/**
 * camera-capture.js — Client-side image compression + Alpine.js camera component.
 *
 * Provides:
 *   compressImage(file, maxDim, quality) — resize + JPEG compress
 *   cameraCapture() — Alpine.js component for the FAB → shooting → categorize flow
 */

// ── Image compression ────────────────────────────────────────────────────────

/**
 * Compress an image file to JPEG, capping dimensions at maxDim.
 * Falls back to original file if Canvas can't decode (e.g. HEIC on some browsers).
 *
 * @param {File|Blob} file
 * @param {number} maxDim  - Max width or height in pixels (default 1920)
 * @param {number} quality - JPEG quality 0–1 (default 0.82)
 * @returns {Promise<Blob>}
 */
function compressImage(file, maxDim, quality) {
  maxDim = maxDim || 1920;
  quality = quality || 0.82;
  return new Promise(function(resolve) {
    var img = new Image();
    img.onload = function() {
      var w = img.width, h = img.height;
      var ratio = Math.min(maxDim / w, maxDim / h, 1);
      var cw = Math.round(w * ratio);
      var ch = Math.round(h * ratio);
      var canvas = document.createElement('canvas');
      canvas.width = cw;
      canvas.height = ch;
      canvas.getContext('2d').drawImage(img, 0, 0, cw, ch);
      canvas.toBlob(function(blob) {
        URL.revokeObjectURL(img.src);
        resolve(blob || file);
      }, 'image/jpeg', quality);
    };
    img.onerror = function() {
      URL.revokeObjectURL(img.src);
      resolve(file); // fallback
    };
    img.src = URL.createObjectURL(file);
  });
}

// Make available globally
window.compressImage = compressImage;

// ── Alpine.js camera component ───────────────────────────────────────────────

function cameraCapture() {
  return {
    // State machine: idle → shooting → categorizing → (delivery_detail|issue_detail) → done
    state: 'idle',

    // Batch data
    batchUuid: null,
    photos: [],       // { blob, preview, mediaUuid }
    latitude: null,
    longitude: null,
    gpsTimestamp: 0,

    // Job inference
    clientId: null,
    clientName: null,
    projectId: null,
    inferMethod: 'none',
    clientList: [],    // fallback picker

    // Category
    category: 'uncategorized',

    // Delivery sub-flow
    supplier: '',
    costCodeId: null,
    costCodes: [],
    quantityNote: '',

    // Issue sub-flow
    issueTitle: '',
    issueDescription: '',
    issuePriority: 'Medium',

    // ── Actions ──────────────────────────────────────────────────────────

    open() {
      this.batchUuid = crypto.randomUUID ? crypto.randomUUID() : this._uuid();
      this.photos = [];
      this.category = 'uncategorized';
      this.supplier = '';
      this.costCodeId = null;
      this.quantityNote = '';
      this.issueTitle = '';
      this.issueDescription = '';
      this.issuePriority = 'Medium';
      this.state = 'shooting';

      this._requestGPS();
      this._inferJob();

      // Trigger camera after short delay for overlay to render
      var self = this;
      setTimeout(function() { self._triggerCamera(); }, 200);
    },

    close() {
      this.state = 'idle';
      this.photos.forEach(function(p) {
        if (p.preview) URL.revokeObjectURL(p.preview);
      });
      this.photos = [];
    },

    // ── Shooting ─────────────────────────────────────────────────────────

    _triggerCamera() {
      var input = this.$refs.cameraInput;
      if (input) {
        input.value = '';
        input.click();
      }
    },

    async onFileSelected(event) {
      var files = event.target.files;
      if (!files || !files.length) return;

      for (var i = 0; i < files.length; i++) {
        var compressed = await compressImage(files[i]);
        var mediaUuid = crypto.randomUUID ? crypto.randomUUID() : this._uuid();
        var preview = URL.createObjectURL(compressed);

        this.photos.push({ blob: compressed, preview: preview, mediaUuid: mediaUuid });

        // Enqueue to IndexedDB immediately
        if (window.FieldQueue) {
          await FieldQueue.enqueueMedia(this.batchUuid, compressed, {
            media_uuid: mediaUuid,
            latitude: this.latitude,
            longitude: this.longitude,
            taken_at: new Date().toISOString(),
          });
        }
      }

      // Rapid-fire: re-trigger camera after brief pause
      if (this.state === 'shooting') {
        var self = this;
        setTimeout(function() { self._triggerCamera(); }, 300);
      }
    },

    doneShooting() {
      if (this.photos.length === 0) {
        this.close();
        return;
      }
      this.state = 'categorizing';
    },

    // ── Categorizing ─────────────────────────────────────────────────────

    selectCategory(cat) {
      this.category = cat;
      if (cat === 'delivery') {
        this._loadCostCodes();
        this.state = 'delivery_detail';
      } else if (cat === 'issue') {
        this.issueTitle = 'Issue at ' + (this.clientName || 'jobsite');
        this.state = 'issue_detail';
      } else {
        this._enqueueBatch();
      }
    },

    skipCategory() {
      this.category = 'uncategorized';
      this._enqueueBatch();
    },

    // ── Delivery sub-flow ────────────────────────────────────────────────

    async _loadCostCodes() {
      if (!this.clientId) return;
      try {
        var resp = await fetch('/api/camera/cost-codes?client_id=' + this.clientId);
        if (resp.ok) {
          var data = await resp.json();
          this.costCodes = data.cost_codes || [];
        }
      } catch(e) { /* offline — proceed without codes */ }
    },

    saveDelivery() {
      // Save supplier to localStorage for autocomplete
      if (this.supplier) {
        var recent = JSON.parse(localStorage.getItem('recent_suppliers') || '[]');
        if (recent.indexOf(this.supplier) === -1) {
          recent.unshift(this.supplier);
          if (recent.length > 10) recent = recent.slice(0, 10);
          localStorage.setItem('recent_suppliers', JSON.stringify(recent));
        }
      }
      this._enqueueBatch();
    },

    getRecentSuppliers() {
      return JSON.parse(localStorage.getItem('recent_suppliers') || '[]');
    },

    // ── Issue sub-flow ───────────────────────────────────────────────────

    saveIssue() {
      if (!this.issueTitle.trim()) this.issueTitle = 'Issue at jobsite';
      this._enqueueBatch();
    },

    // ── Batch enqueue ────────────────────────────────────────────────────

    async _enqueueBatch() {
      var batchData = {
        client_id: this.clientId,
        project_id: this.projectId,
        category: this.category,
        photo_count: this.photos.length,
        latitude: this.latitude,
        longitude: this.longitude,
      };

      if (this.category === 'delivery') {
        batchData.supplier = this.supplier;
        batchData.cost_code_id = this.costCodeId;
        batchData.quantity_note = this.quantityNote;
      } else if (this.category === 'issue') {
        batchData.issue_title = this.issueTitle;
        batchData.issue_description = this.issueDescription;
        batchData.priority = this.issuePriority;
      }

      if (window.FieldQueue) {
        await FieldQueue.enqueue('photo_batch', batchData, { clientUuid: this.batchUuid });
      }

      this.state = 'done';
      var self = this;
      setTimeout(function() { self.close(); }, 2000);
    },

    // ── Job inference ────────────────────────────────────────────────────

    async _inferJob() {
      try {
        var url = '/api/camera/infer-job';
        if (this.latitude && this.longitude) {
          url += '?lat=' + this.latitude + '&lng=' + this.longitude;
        }
        var resp = await fetch(url);
        if (!resp.ok) return;
        var data = await resp.json();
        this.inferMethod = data.method;
        if (data.client_id) {
          this.clientId = data.client_id;
          this.clientName = data.client_name;
          this.projectId = data.project_id;
        }
        if (data.clients) {
          this.clientList = data.clients;
        }
      } catch(e) { /* offline — user picks manually */ }
    },

    pickClient(c) {
      this.clientId = c.client_id;
      this.clientName = c.name;
      this.projectId = c.project_id;
      this.inferMethod = 'manual';
    },

    // ── GPS ──────────────────────────────────────────────────────────────

    _requestGPS() {
      // Cache GPS for 60 seconds
      if (this.latitude && (Date.now() - this.gpsTimestamp) < 60000) return;

      if (!navigator.geolocation) return;
      var self = this;
      navigator.geolocation.getCurrentPosition(
        function(pos) {
          self.latitude = pos.coords.latitude;
          self.longitude = pos.coords.longitude;
          self.gpsTimestamp = Date.now();
          // Re-infer job if we got GPS after initial infer
          if (self.inferMethod === 'none') {
            self._inferJob();
          }
        },
        function() { /* GPS denied — continue without */ },
        { enableHighAccuracy: true, timeout: 10000 }
      );
    },

    // ── Helpers ──────────────────────────────────────────────────────────

    _uuid() {
      return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = (Math.random() * 16) | 0;
        return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
      });
    },

    get photoCountLabel() {
      var n = this.photos.length;
      return n === 1 ? '1 photo' : n + ' photos';
    },

    get lastPhotos() {
      return this.photos.slice(-4);
    },
  };
}

// Make component available globally for Alpine
window.cameraCapture = cameraCapture;
