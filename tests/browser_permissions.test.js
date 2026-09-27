const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const tick = () => new Promise(resolve => setImmediate(resolve));

async function background(initial = {}) {
  const h = { permissions: {}, host: true, network: 0, preferences: [], tabs: [], checks: 0, alarms: [], ...initial };
  const events = {};
  const event = name => ({ addListener: fn => { events[name] = fn; } });
  let options;
  class Engine {
    constructor(o) {
      options = o; this.config = o.config;
      this.cache = { state: async () => ({ consented: h.consented !== false, automatic: Boolean(h.automatic),
        nextDue: h.nextDue || 0, manualAfter: 0 }) };
    }
    configured() { return true; }
    consentDecisionPending() { return Promise.resolve(Boolean(h.pending)); }
    preferences(...args) { h.preferences.push(args); return Promise.resolve(); }
    check() { h.checks++; return Promise.resolve(); }
  }
  const chrome = {
    runtime: { id: "test", getURL: p => "moz-extension://test/" + p,
      getManifest: () => ({ version: "2.6.0" }), onMessage: event("message"),
      onStartup: event("startup"), onInstalled: event("installed") },
    alarms: { onAlarm: event("alarm"), get: (name, cb) => cb(h.alarm),
      create: (name, info) => { h.alarms.push(info.when); h.alarm = { name, scheduledTime: info.when }; },
      clear: () => { h.alarm = undefined; } },
    permissions: { onRemoved: event("removed"), contains: (_, cb) => cb(h.host),
      getAll: cb => {
        if (h.permissionError) chrome.runtime.lastError = { message: "API failure" };
        cb(h.permissions); delete chrome.runtime.lastError;
      } },
    tabs: { create: tab => h.tabs.push(tab) }
  };
  const fetch = async url => {
    if (url.startsWith("moz-extension:")) return { ok: true, json: async () => ({ origin: "https://data.example.org/data/", trusted_keys: {} }) };
    h.network++; return { ok: true };
  };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../extension/js/data-background.js"), "utf8"),
    { chrome, fetch, URL, DTUDataEngine: Engine, DTUDataCache: class {} });
  await tick();
  h.download = () => options.fetcher("https://data.example.org/data/current.json", {});
  h.events = events;
  return h;
}

test("Firefox download checks personal-data consent without requiring technical telemetry", async () => {
  const h = await background();
  h.permissions = { data_collection: ["technicalAndInteraction"] };
  await assert.rejects(h.download(), /consent/);
  assert.equal(h.network, 0);
  h.permissions = { data_collection: ["personallyIdentifyingInfo"] };
  await h.download();
  assert.equal(h.network, 1);
  h.permissions = { data_collection: [] };
  await assert.rejects(h.download(), /consent/);
  assert.equal(h.network, 1);
});

test("Chrome and older Firefox use host access and permission errors fail closed", async () => {
  const h = await background();
  await h.download();
  h.host = false;
  await assert.rejects(h.download(), /host access/);
  h.host = true; h.permissionError = true;
  await assert.rejects(h.download(), /could not be checked/);
  assert.equal(h.network, 1);
});

test("revoking download permission disables preferences; unrelated telemetry does not", async () => {
  const h = await background();
  h.events.removed({ data_collection: ["technicalAndInteraction"] });
  await tick(); assert.equal(h.preferences.length, 0);
  h.events.removed({ data_collection: ["personallyIdentifyingInfo"] });
  await tick(); assert.deepEqual(h.preferences, [[false, false]]);
  h.host = false;
  h.events.removed({ origins: ["<all_urls>"] });
  await tick(); assert.deepEqual(h.preferences, [[false, false], [false, false]]);
});

test("consent page opens only for installation or extension update without a recorded choice", async () => {
  const h = await background();
  h.pending = true;
  h.events.installed({ reason: "chrome_update" });
  await tick(); assert.equal(h.tabs.length, 0); assert.equal(h.checks, 0);
  h.events.installed({ reason: "update" });
  await tick(); assert.equal(h.tabs.length, 1); assert.equal(h.tabs[0].active, true);
  // Accepting or declining under the current disclosure is not prompted again on later updates.
  h.pending = false;
  h.events.installed({ reason: "update" });
  await tick(); assert.equal(h.tabs.length, 1);
});

test("worker restarts do not postpone a pending automatic check", async () => {
  const soon = Date.now() + 30000;
  const kept = await background({ automatic: true, alarm: { name: "dtu-course-data-check", scheduledTime: soon } });
  assert.deepEqual(kept.alarms, []); assert.equal(kept.alarm.scheduledTime, soon);
  const due = Date.now() + 86400000;
  const late = await background({ automatic: true, nextDue: due, alarm: { name: "dtu-course-data-check", scheduledTime: due + 86400000 } });
  assert.deepEqual(late.alarms, [due]);
  const missing = await background({ automatic: true });
  assert.equal(missing.alarms.length, 1); assert(missing.alarm.scheduledTime >= Date.now() + 59000);
  // After the one-shot alarm fires, the next check is scheduled again.
  missing.alarm = undefined;
  missing.events.alarm({ name: "dtu-course-data-check" });
  await tick(); await tick();
  assert.equal(missing.checks, 1); assert.equal(missing.alarms.length, 2);
  const manual = await background({ automatic: false, alarm: { name: "dtu-course-data-check", scheduledTime: soon } });
  assert.equal(manual.alarm, undefined);
});

test("consent UI requests only download-related permissions and preserves refusal", async () => {
  for (const modern of [false, true]) {
    for (const granted of [false, true]) {
      const elements = new Map(), requests = [], writes = [];
      const get = id => {
        if (!elements.has(id)) elements.set(id, { checked: false, handlers: {},
          addEventListener(name, fn) { this.handlers[name] = fn; } });
        return elements.get(id);
      };
      const view = { configured: true, origin: "https://data.example.org/data/", state: { consented: false, automatic: false } };
      const chrome = { runtime: {}, permissions: {
        getAll: cb => cb(modern ? { data_collection: [] } : {}),
        request: (permissions, cb) => { requests.push(JSON.parse(JSON.stringify(permissions))); cb(granted); }
      } };
      const DTUData = { status: () => "Bundled", subscribe() {}, message: async (type, fields) => {
        if (type === "courseDataPreferences") writes.push(fields);
        return view;
      } };
      vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../extension/js/data-controls.js"), "utf8"),
        { chrome, DTUData, document: { getElementById: get }, URL });
      await tick();
      get("data-download-consent").checked = true;
      get("data-download-consent").handlers.change();
      await tick();
      assert.deepEqual(requests, [{ origins: ["https://data.example.org/*"],
        ...(modern ? { data_collection: ["personallyIdentifyingInfo"] } : {}) }]);
      assert.equal(writes.length, granted ? 1 : 0);
      if (granted) { assert.equal(writes[0].consented, true); assert.equal(writes[0].automatic, false); }
      else assert.equal(get("data-download-consent").checked, false);
    }
  }
});
