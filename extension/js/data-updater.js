// Background-only storage and update engine. No page-supplied network destinations.
(function (root) {
  "use strict";
  const DAY = 86400000;
  const defaults = () => ({ consented: false, automatic: false, highest: 0, epoch: 0, failures: 0, nextDue: 0, manualAfter: 0, lastSuccess: null });
  class Cache {
    async open() {
      if (!this.db) this.db = new Promise((resolve, reject) => {
        const request = indexedDB.open("dtu-course-data-v1", 1);
        request.onupgradeneeded = () => request.result.createObjectStore("records");
        request.onsuccess = () => { request.result.onversionchange = () => request.result.close(); resolve(request.result); };
        request.onerror = () => reject(request.error);
        request.onblocked = () => reject(new Error("Course cache is blocked by another extension page"));
      });
      return this.db;
    }
    async transaction(mode, work) {
      const db = await this.open();
      return new Promise((resolve, reject) => {
        const tx = db.transaction("records", mode), records = tx.objectStore("records");
        let result;
        tx.oncomplete = () => resolve(result);
        tx.onerror = tx.onabort = () => reject(tx.error || new Error("Course cache write failed"));
        try { work(records, value => { result = value; }, tx); } catch (e) { tx.abort(); reject(e); }
      });
    }
    get(key) {
      return this.transaction("readonly", (records, done) => {
        const request = records.get(key); request.onsuccess = () => done(request.result);
      });
    }
    async state() {
      const s = await this.get("state");
      if (s === undefined) return defaults();
      DTURelease.assert(s && Number.isSafeInteger(s.highest) && s.highest >= 0 && Number.isSafeInteger(s.epoch) &&
        typeof s.consented === "boolean" && typeof s.automatic === "boolean" &&
        Number.isFinite(s.nextDue) && Number.isFinite(s.manualAfter), "Corrupt cache state");
      return s;
    }
    async change(fn) {
      await this.state();
      return this.transaction("readwrite", (records, done, tx) => {
        const request = records.get("state");
        request.onsuccess = () => {
          try {
            const next = fn(request.result || defaults());
            records.put(next, "state"); done(next);
          } catch (e) { tx.abort(); }
        };
      });
    }
    stage(record) {
      return this.transaction("readwrite", (records) => records.put(record, "candidate"));
    }
    async activate(record, metadata, envelopeHash, epoch) {
      await this.state();
      return this.transaction("readwrite", (records, done, tx) => {
        const request = records.get("state");
        request.onsuccess = () => {
          try {
            const s = request.result || defaults();
            DTURelease.assert(s.consented && s.epoch === epoch && metadata.sequence >= s.highest, "Update was cancelled or superseded");
            const previous = s.active && s.active !== metadata.sequence ? s.active : s.previous;
            if (s.previous && s.previous !== previous && s.previous !== metadata.sequence) records.delete("release:" + s.previous);
            records.put(record, "release:" + metadata.sequence);
            records.delete("candidate");
            const next = { ...s, previous, active: metadata.sequence, highest: metadata.sequence,
              highestDigest: metadata.sha256, highestEnvelope: envelopeHash,
              lastSuccess: Date.now(), failures: 0, error: null };
            records.put(next, "state"); done(next);
          } catch (e) { tx.abort(); }
        };
      });
    }
    async clear() {
      await this.state();
      return this.transaction("readwrite", (records, done) => {
        const request = records.get("state");
        request.onsuccess = () => {
          const next = { ...(request.result || defaults()), active: null, previous: null, error: null, lastSuccess: null };
          records.clear(); records.put(next, "state"); done(next);
        };
      });
    }
  }
  class Engine {
    constructor({ config, policy, cache, bundled, fetcher = fetch, notify = async () => {}, now = Date.now, random = Math.random }) {
      Object.assign(this, { config, policy, cache, bundled, fetcher, notify, now, random });
      this.flight = null; this.snapshot = null;
    }
    configured() { return Boolean(this.config.origin && Object.keys(this.config.trusted_keys).length); }
    async read() {
      let s;
      try {
        s = await this.cache.state();
        if (!s.consented) return await this.fallback(s);
        if (this.snapshot) return { ...this.snapshot, state: s };
        for (const sequence of [s.active, s.previous].filter(Boolean)) {
          try {
            const record = await this.cache.get("release:" + sequence);
            DTURelease.assert(record, "Missing cached release");
            const metadata = await DTURelease.envelope(record.envelope, this.config);
            DTURelease.assert(metadata.sequence === sequence && sequence <= s.highest, "Corrupt cached sequence");
            if (sequence === s.highest) DTURelease.assert(metadata.sha256 === s.highestDigest &&
              await DTURelease.digest(record.envelope) === s.highestEnvelope, "Corrupt accepted release");
            const data = await DTURelease.payload(record.payload, metadata, this.policy);
            this.snapshot = { data, metadata, generation: String(sequence), source: sequence === s.active ? "downloaded" : "last-known-good" };
            return { ...this.snapshot, state: s };
          } catch (_) { /* Try the retained working generation, then the bundle. */ }
        }
        return await this.fallback({ ...s, error: s.active ? "Saved data could not be verified; using bundled data." : s.error });
      } catch (_) {
        return await this.fallback({ ...defaults(), error: "Local cache is unavailable; using bundled data." });
      }
    }
    async fallback(s) {
      const data = await this.bundled();
      const collected = Object.values(data).map(c => c.history_collected_at).filter(Boolean).sort()[0];
      return { data, metadata: { collected_at: collected }, generation: "bundled", source: "bundled", state: s };
    }
    async preferences(consented, automatic) {
      DTURelease.assert(typeof consented === "boolean" && typeof automatic === "boolean", "Invalid download preference");
      if (!consented && this.controller) this.controller.abort();
      const state = await this.cache.change(s => ({ ...s, consented, automatic: consented && automatic, epoch: s.epoch + 1 }));
      this.snapshot = null;
      await this.notify();
      return state;
    }
    async clear() {
      if (this.controller) this.controller.abort();
      await this.cache.change(s => ({ ...s, epoch: s.epoch + 1 }));
      await this.cache.clear();
      this.snapshot = null;
      await this.notify();
    }
    check(manual = false) {
      if (!this.flight) this.flight = this.perform(manual).finally(() => { this.flight = null; this.controller = null; });
      return this.flight;
    }
    async perform(manual) {
      if (!this.configured()) return { updated: false, reason: "Remote updates are not configured in this build." };
      const time = this.now();
      let reserved = false;
      const state = await this.cache.change(s => {
        if (!s.consented || (!manual && (!s.automatic || time < s.nextDue)) || time < s.manualAfter) return s;
        reserved = true;
        return { ...s, lastAttempt: time, nextDue: time + DAY + Math.floor(this.random() * 3600000),
          manualAfter: time + Math.min(3600000, 300000 * (2 ** Math.min(s.failures || 0, 4))) };
      });
      if (!reserved) return { updated: false, reason: "Downloads are disabled or the next check is not due yet." };
      this.controller = new AbortController();
      try {
        const envelope = await DTURelease.download(DTURelease.origin(this.config.origin) + "current.json",
          DTURelease.MAX_ENVELOPE, this.fetcher, this.controller.signal);
        const metadata = await DTURelease.envelope(envelope, this.config);
        const envelopeHash = await DTURelease.digest(envelope);
        DTURelease.assert(metadata.sequence >= state.highest, "An older remote release was rejected.");
        if (metadata.sequence === state.highest) {
          DTURelease.assert(metadata.sha256 === state.highestDigest && envelopeHash === state.highestEnvelope,
            "Release sequence was reused with different metadata.");
          const current = await this.read();
          if (current.generation === String(metadata.sequence)) {
            await this.cache.change(s => ({ ...s, lastSuccess: this.now(), failures: 0, error: null }));
            return { updated: false, reason: "The current dataset is already installed." };
          }
        }
        const beforePayload = await this.cache.state();
        DTURelease.assert(beforePayload.consented && beforePayload.epoch === state.epoch, "Update cancelled.");
        const payload = await DTURelease.download(this.config.origin + metadata.path, DTURelease.MAX_PAYLOAD, this.fetcher, this.controller.signal);
        const data = await DTURelease.payload(payload, metadata, this.policy);
        const record = { envelope, payload };
        await this.cache.stage(record);
        await this.cache.activate(record, metadata, envelopeHash, state.epoch);
        this.snapshot = { data, metadata, generation: String(metadata.sequence), source: "downloaded" };
        await this.notify().catch(() => {});
        return { updated: true, reason: "Verified course data activated." };
      } catch (error) {
        await this.cache.change(s => ({ ...s, failures: Math.min(10, (s.failures || 0) + 1),
          error: "Update failed; previous or bundled data remains available. " + error.message }));
        await this.notify().catch(() => {});
        return { updated: false, reason: error.message };
      }
    }
  }
  root.DTUDataCache = Cache;
  root.DTUDataEngine = Engine;
  if (typeof module !== "undefined") module.exports = { Cache, Engine };
})(globalThis);
