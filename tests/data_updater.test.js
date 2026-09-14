const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const { IDBFactory } = require("fake-indexeddb");
global.DTURelease = require("../extension/js/data-contract.js");
const { Cache, Engine } = require("../extension/js/data-updater.js");
const policy = JSON.parse(fs.readFileSync(path.join(__dirname, "../extension/js/data-schema-policy.json")));
const fixtureRoot = path.join(__dirname, "fixtures/course-data-release");
const sampleEnvelope = fs.readFileSync(path.join(fixtureRoot, "current.json"));
const template = JSON.parse(Buffer.from(JSON.parse(sampleEnvelope).metadata, "base64"));
const samplePayload = fs.readFileSync(path.join(fixtureRoot, "data.json"));
const pair = crypto.generateKeyPairSync("rsa", { modulusLength: 3072, publicExponent: 65537 });
const config = { origin: template.origin, channel: "staging", trusted_keys: {
  test: pair.publicKey.export({ type: "spki", format: "der" }).toString("base64")
} };
function signed(sequence = 1, payload = samplePayload, change = {}) {
  const metadata = { ...template, key_id: "test", sequence, request_id: "test-" + sequence,
    byte_length: payload.length, sha256: crypto.createHash("sha256").update(payload).digest("hex"), ...change };
  metadata.path = "releases/" + metadata.sequence + "-" + metadata.sha256 + "/data.json";
  const raw = Buffer.from(JSON.stringify(metadata));
  const envelope = Buffer.from(JSON.stringify({ key_id: "test", metadata: raw.toString("base64"),
    signature: crypto.sign("RSA-SHA256", raw, pair.privateKey).toString("base64") }));
  return { metadata, payload: new Uint8Array(payload), envelope: new Uint8Array(envelope) };
}
function response(url, payload) {
  return { status: 200, ok: true, url, redirected: false, body: new ReadableStream({
    start(controller) { controller.enqueue(new Uint8Array(payload)); controller.close(); }
  }) };
}
async function harness(release = signed()) {
  global.indexedDB = new IDBFactory();
  const cache = new Cache();
  const calls = [];
  let current = release, now = Date.now();
  const options = { config, policy, cache, bundled: async () => JSON.parse(samplePayload), now: () => now, random: () => 0,
    fetcher: async (url, options) => {
      calls.push({ url, options });
      if (current instanceof Error) throw current;
      return response(url, url.endsWith("current.json") ? current.envelope : current.payload);
    } };
  const engine = new Engine(options);
  return { cache, engine, options, calls, set: r => { current = r; }, advance: (ms = 86400001) => { now += ms; } };
}
test("default and upgrading installations make no request before affirmative consent", async () => {
  const h = await harness();
  await h.engine.check(true); await h.engine.check();
  assert.equal(h.calls.length, 0);
  assert.equal((await h.engine.read()).source, "bundled");
});
test("old disclosure consent cannot authorize downloads after upgrade", async () => {
  const h = await harness();
  await h.engine.preferences(true, true);
  await h.cache.change(s => ({ ...s, consentRevision: 1, highest: 7 }));
  assert.equal((await h.cache.state()).consented, false);
  await h.engine.check(); await h.engine.check(true);
  assert.equal(h.calls.length, 0);
  assert.equal((await h.engine.read()).source, "bundled");
  assert.equal((await h.cache.state()).highest, 7);
  await h.engine.preferences(true, false);
  assert.equal((await new Engine(h.options).cache.state()).consented, true);
});
test("valid activation is atomic and survives a terminated background", async () => {
  const h = await harness();
  await h.engine.preferences(true, true);
  assert.equal((await h.engine.check()).updated, true);
  assert.equal((await h.engine.read()).generation, "1");
  const restarted = new Engine(h.options);
  assert.equal((await restarted.read()).generation, "1");
  await restarted.check();
  assert.equal(h.calls.length, 2);
  assert.equal((await h.cache.state()).highest, 1);
});
test("daily schedule, persisted cooldown and single flight avoid request storms", async () => {
  const h = await harness();
  await h.engine.preferences(true, true);
  const results = await Promise.all(Array.from({ length: 20 }, () => h.engine.check(true)));
  assert(results.every(r => r.updated));
  assert.equal(h.calls.length, 2);
  await h.engine.check(true); await h.engine.check();
  assert.equal(h.calls.length, 2);
  h.advance();
  assert.equal((await h.engine.check()).updated, false);
  assert.equal(h.calls.length, 3);
});
test("tampering, older releases and reused sequences never replace working data", async () => {
  const h = await harness(signed(2));
  await h.engine.preferences(true, true); await h.engine.check(true);
  const bad = signed(3); bad.payload[0] ^= 1;
  for (const next of [bad, signed(1), signed(2, samplePayload, { request_id: "changed" })]) {
    h.set(next); h.advance();
    assert.equal((await h.engine.check(true)).updated, false);
    assert.equal((await h.engine.read()).generation, "2");
    assert.equal((await h.cache.state()).highest, 2);
  }
});
test("forward rollback, cache corruption and clearing retain a safe fallback and high watermark", async () => {
  const h = await harness();
  await h.engine.preferences(true, true); await h.engine.check(true);
  h.set(signed(2)); h.advance(); await h.engine.check(true);
  const active = await h.cache.get("release:2"); active.payload[0] ^= 1;
  await h.cache.transaction("readwrite", records => records.put(active, "release:2"));
  const restarted = new Engine(h.options);
  const fallback = await restarted.read();
  assert.equal(fallback.source, "last-known-good"); assert.equal(fallback.generation, "1");
  h.set(signed(3)); h.advance(); assert.equal((await restarted.check(true)).updated, true);
  await restarted.clear();
  assert.equal((await restarted.read()).source, "bundled");
  assert.equal((await h.cache.state()).highest, 3);
  h.set(signed(2)); h.advance();
  assert.equal((await restarted.check(true)).updated, false);
  assert.equal((await restarted.read()).source, "bundled");
});
test("storage exhaustion and offline failures leave active data untouched", async () => {
  const h = await harness();
  await h.engine.preferences(true, true); await h.engine.check(true);
  const stage = h.cache.stage.bind(h.cache);
  h.cache.stage = async () => { throw new Error("QuotaExceededError"); };
  h.set(signed(2)); h.advance(); await h.engine.check(true);
  assert.equal((await h.engine.read()).generation, "1");
  h.cache.stage = stage;
  h.set(new Error("offline")); h.advance(); await h.engine.check(true);
  assert.equal((await new Engine(h.options).read()).generation, "1");
});
test("revoking consent during a download cancels activation", async () => {
  const h = await harness();
  await h.engine.preferences(true, true);
  const original = h.engine.fetcher;
  h.engine.fetcher = async (url, options) => {
    if (url.endsWith("data.json")) await h.engine.preferences(false, false);
    return original(url, options);
  };
  assert.equal((await h.engine.check(true)).updated, false);
  assert.equal((await h.cache.state()).highest, 0);
  assert.equal((await h.engine.read()).source, "bundled");
});
test("requests omit credentials, referrers and all browsing information", async () => {
  const h = await harness();
  await h.engine.preferences(true, false); await h.engine.check(true);
  assert.equal(h.calls.length, 2);
  for (const call of h.calls) {
    assert(call.url.startsWith(config.origin));
    assert(!call.url.includes("?"));
    assert.equal(call.options.credentials, "omit");
    assert.equal(call.options.referrerPolicy, "no-referrer");
    assert.equal(call.options.redirect, "error");
    assert.equal(call.options.cache, "no-cache");
  }
});
test("streamed sizes and redirect attempts are bounded before activation", async () => {
  await assert.rejects(DTURelease.download(config.origin, 10, async url => response(url, new Uint8Array(11))), /byte limit/);
  await assert.rejects(DTURelease.download(config.origin, 10, async url => ({ ...response(url, new Uint8Array()), redirected: true })), /response/);
});
test("schema rejects malicious links, prototype keys, nonfinite values and incompatible metadata", async () => {
  for (const json of ['{"__proto__":{}}', '{"a":1,"a":2}', '{"constructor":{}}']) {
    assert.throws(() => DTURelease.parse(Buffer.from(json), 100), /key/);
  }
  for (const change of [d => { d["01001"].avg = Infinity; },
    d => { d["01001"].exam_history[0].grade_source = "javascript:alert(1)"; },
    d => { d["01001"].grades["12"] = -1; }]) {
    const data = JSON.parse(samplePayload); change(data);
    assert.throws(() => DTURelease.dataset(Buffer.from(JSON.stringify(data)), policy));
  }
  const invalid = signed(1, samplePayload, { compatibility: {} });
  await assert.rejects(DTURelease.envelope(invalid.envelope, config), /compatibility/);
  await assert.rejects(DTURelease.envelope(signed().envelope, { ...config, trusted_keys: {} }), /key/);
});
test("real dataset and Python signed sample verify under the browser contract", async () => {
  const real = fs.readFileSync(path.join(__dirname, "../extension/db/data.json"));
  assert.deepEqual(DTURelease.dataset(real, policy), JSON.parse(real));
  const sampleConfig = { origin: template.origin, channel: "staging", trusted_keys: JSON.parse(fs.readFileSync(path.join(fixtureRoot, "public-keys.json"))) };
  const metadata = await DTURelease.envelope(sampleEnvelope, sampleConfig);
  await DTURelease.payload(samplePayload, metadata, policy);
});

test("installed compatibility and unsupported signed field types fail closed", async () => {
  await assert.rejects(DTURelease.envelope(signed().envelope, { ...config, clientVersion: "2.5.0" }), /Installed extension/);
  await DTURelease.envelope(signed().envelope, { ...config, clientVersion: "2.6.0" });
  await assert.rejects(DTURelease.envelope(signed(1, samplePayload, { request_id: null }).envelope, config), /identity/);
});

test("staged candidates are never active after an interrupted background", async () => {
  const h = await harness();
  await h.engine.preferences(true, true);
  const record = signed();
  await h.cache.stage({ envelope: record.envelope, payload: record.payload });
  assert.equal((await new Engine(h.options).read()).generation, "bundled");
  assert.equal((await h.cache.state()).highest, 0);
});

test("IndexedDB clear preserves concurrent preference changes and anti-rollback state", async () => {
  const h = await harness();
  await h.engine.preferences(true, true); await h.engine.check(true);
  await Promise.all([h.engine.clear(), h.engine.preferences(false, false)]);
  assert.equal((await h.cache.state()).consented, false);
  assert.equal((await h.cache.state()).highest, 1);
  assert.equal((await h.engine.read()).source, "bundled");
});

test("course pages cannot invoke privileged update controls or supply fetch URLs", async () => {
  const vm = require("node:vm");
  const listeners = [];
  let checks = 0;
  class FakeEngine {
    constructor(options) { this.config = options.config; this.cache = { state: async () => ({ consented: false, automatic: false }) }; }
    configured() { return false; }
    read() { return Promise.resolve({ data: { "01001": { name: "Course" } }, generation: "bundled", metadata: {}, state: {} }); }
    check() { checks++; return Promise.resolve({ updated: false }); }
  }
  const event = { addListener() {} };
  const chrome = {
    runtime: { id: "test", getURL: p => "chrome-extension://test/" + p, getManifest: () => ({ version: "2.6.0" }),
      onMessage: { addListener: fn => listeners.push(fn) }, onStartup: event, onInstalled: event, sendMessage() {} },
    alarms: { onAlarm: event, create() {}, clear() {} },
    permissions: { onRemoved: event, getAll: callback => callback({}) },
    tabs: { query: (_, cb) => cb([]), sendMessage() {}, create() {} }
  };
  const context = vm.createContext({ chrome, DTUDataEngine: FakeEngine, DTUDataCache: class {},
    fetch: async () => ({ ok: true, json: async () => ({ origin: null, trusted_keys: {} }) }), URL, console });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../extension/js/data-background.js"), "utf8"), context);
  const send = (message, url, tab) => new Promise(resolve => listeners[0](message, { id: "test", url, tab }, resolve));
  const denied = await send({ type: "courseDataCheck", url: "https://evil.example/" }, "https://kurser.dtu.dk/course/01001");
  assert.match(denied.error, /only in the extension/); assert.equal(checks, 0);
  const data = await send({ type: "courseDataGet", courseId: "01001", url: "https://evil.example/" }, "https://kurser.dtu.dk/course/01001");
  assert.equal(data.data.name, "Course"); assert.equal(checks, 0);
  await send({ type: "courseDataCheck" }, "chrome-extension://test/db.html#compare");
  assert.equal(checks, 1);
  const privateResult = await send({ type: "courseDataGet", courseId: "01001" }, "https://kurser.dtu.dk/course/01001", { incognito: true });
  assert.match(privateResult.error, /Private windows/);
});

test("the complete real payload survives IndexedDB activation and restart", async () => {
  const real = fs.readFileSync(path.join(__dirname, "../extension/db/data.json"));
  const h = await harness(signed(1, real));
  await h.engine.preferences(true, true);
  assert.equal((await h.engine.check(true)).updated, true);
  const restored = await new Engine(h.options).read();
  assert.equal(restored.generation, "1");
  assert.deepEqual(restored.data, JSON.parse(real));
});
