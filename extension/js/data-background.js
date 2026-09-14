// Runs in a Chrome service worker or Firefox's nonpersistent background page.
(function () {
  "use strict";
  const alarmName = "dtu-course-data-check";
  const localJSON = async path => {
    const response = await fetch(chrome.runtime.getURL(path));
    if (!response.ok) throw new Error("Packaged update configuration is unavailable");
    return response.json();
  };
  const notify = async () => {
    const message = { type: "courseDataChanged" };
    chrome.runtime.sendMessage(message, () => { void chrome.runtime.lastError; });
    chrome.tabs.query({ url: "https://kurser.dtu.dk/course/*" }, tabs => {
      if (chrome.runtime.lastError) return;
      for (const tab of tabs || []) chrome.tabs.sendMessage(tab.id, message, () => { void chrome.runtime.lastError; });
    });
  };
  let bundled;
  const ready = Promise.all([localJSON("js/data-update-config.json"), localJSON("js/data-schema-policy.json")]).then(([config, policy]) =>
    new DTUDataEngine({ config: { ...config, clientVersion: chrome.runtime.getManifest().version }, policy, cache: new DTUDataCache(), notify,
      fetcher: async (url, options) => {
        const permissions = await new Promise(resolve => chrome.permissions.getAll(resolve));
        if (permissions.data_collection && !permissions.data_collection.includes("technicalAndInteraction")) {
          throw new Error("Firefox download consent is not granted.");
        }
        return fetch(url, options);
      },
      bundled: () => bundled || (bundled = localJSON("db/data.json").catch(e => { bundled = null; throw e; })) }));
  async function schedule() {
    const engine = await ready;
    const s = await engine.cache.state();
    if (engine.configured() && s.consented && s.automatic) {
      chrome.alarms.create(alarmName, { when: Math.max(Date.now() + 60000, s.nextDue || 0, s.manualAfter || 0) });
    } else chrome.alarms.clear(alarmName);
  }
  function privileged(sender) {
    return sender.id === chrome.runtime.id && typeof sender.url === "string" && sender.url.split("#")[0] === chrome.runtime.getURL("db.html");
  }
  chrome.runtime.onMessage.addListener((message, sender, respond) => {
    if (!message || !["courseDataGet", "courseDataStatus", "courseDataPreferences", "courseDataCheck", "courseDataClear"].includes(message.type)) return;
    const operation = ready.then(async engine => {
      if (sender.id !== chrome.runtime.id) throw new Error("Untrusted message sender");
      if (message.type === "courseDataGet") {
        const view = await engine.read();
        if (message.courseId !== undefined && !/^[0-9A-Z]{5}$/.test(message.courseId)) throw new Error("Invalid course ID");
        return { data: message.courseId ? view.data[message.courseId] || null : view.data,
          generation: view.generation, metadata: view.metadata, source: view.source, state: view.state };
      }
      if (!privileged(sender)) throw new Error("Update controls are available only in the extension database");
      if (message.type === "courseDataPreferences") await engine.preferences(message.consented, message.automatic);
      if (message.type === "courseDataClear") await engine.clear();
      let result;
      if (message.type === "courseDataCheck") result = await engine.check(true);
      await schedule();
      const view = await engine.read();
      return { configured: engine.configured(), origin: engine.config.origin, state: view.state,
        source: view.source, generation: view.generation, metadata: view.metadata, result };
    });
    operation.then(respond, e => respond({ error: e.message }));
    return true;
  });
  chrome.alarms.onAlarm.addListener(alarm => {
    if (alarm.name === alarmName) ready.then(engine => engine.check()).finally(schedule).catch(() => {});
  });
  const resume = () => ready.then(engine => engine.check()).finally(schedule).catch(() => {});
  chrome.runtime.onStartup.addListener(resume);
  chrome.runtime.onInstalled.addListener(() => {
    ready.then(async engine => {
      if (engine.configured() && !(await engine.cache.state()).consented) chrome.tabs.create({ url: chrome.runtime.getURL("db.html"), active: true });
      resume();
    }).catch(() => {});
  });
  chrome.permissions.onRemoved.addListener(permissions => {
    ready.then(engine => {
      const host = engine.config.origin && new URL(engine.config.origin).origin + "/*";
      if ((permissions.origins || []).includes(host) || (permissions.data_collection || []).includes("technicalAndInteraction")) {
        return engine.preferences(false, false).then(schedule);
      }
    }).catch(() => {});
  });
  // Recreate a missing one-shot alarm after a terminated service worker.
  schedule().catch(() => {});
})();
