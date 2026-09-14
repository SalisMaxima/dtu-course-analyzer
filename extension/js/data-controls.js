(function () {
  "use strict";
  const consent = document.getElementById("data-download-consent");
  const automatic = document.getElementById("data-download-auto");
  const status = document.getElementById("data-update-status");
  const check = document.getElementById("data-check-now");
  let view;
  let builtinDataConsent = false;
  async function refresh() {
    const permissions = await new Promise(resolve => chrome.permissions.getAll(resolve));
    builtinDataConsent = Array.isArray(permissions.data_collection);
    view = await DTUData.message("courseDataStatus");
    consent.checked = view.state.consented;
    automatic.checked = view.state.automatic;
    consent.disabled = !view.configured;
    automatic.disabled = !view.configured || !view.state.consented;
    check.disabled = !view.configured || !view.state.consented;
    const last = view.state.lastSuccess ? new Date(view.state.lastSuccess).toLocaleString() : "never";
    status.textContent = DTUData.status(view) + " · last successful check: " + last +
      (view.configured ? "" : " · downloads are not configured in this build.") +
      (view.state.error ? " " + view.state.error : "");
    if (view.origin) document.getElementById("data-update-disclosure").textContent =
      "Optional updates download the same public dataset from " + new URL(view.origin).hostname +
      " for everyone. The host receives your IP address and request time. Course views, searches, comparison choices and DTU credentials are never sent.";
  }
  async function change(consented, auto) {
    await DTUData.message("courseDataPreferences", { consented, automatic: auto });
    await refresh();
  }
  const failed = error => { status.textContent = "Could not change data settings: " + error.message; };
  consent.addEventListener("change", () => {
    if (!consent.checked) { change(false, false).catch(failed); return; }
    if (!view || !view.configured) return;
    // Host access is requested directly from the user's consent gesture.
    const permissions = { origins: [new URL(view.origin).origin + "/*"] };
    if (builtinDataConsent) permissions.data_collection = ["technicalAndInteraction"];
    chrome.permissions.request(permissions, granted => {
      if (chrome.runtime.lastError || !granted) {
        consent.checked = false;
        status.textContent = "Host access was not granted. Bundled data remains available.";
        return;
      }
      change(true, false).catch(failed);
    });
  });
  automatic.addEventListener("change", () => change(consent.checked, automatic.checked).catch(failed));
  check.addEventListener("click", async () => {
    check.disabled = true; status.textContent = "Checking for a signed course-data release…";
    try {
      const result = await DTUData.message("courseDataCheck");
      await refresh();
      if (result.result) status.textContent += " " + result.result.reason;
    } catch (e) { failed(e); }
    finally { check.disabled = !view || !view.configured || !view.state.consented; }
  });
  document.getElementById("data-use-bundled").addEventListener("click", () => change(false, false).catch(failed));
  document.getElementById("data-clear-cache").addEventListener("click", async () => {
    try { await DTUData.message("courseDataClear"); await refresh(); } catch (e) { failed(e); }
  });
  DTUData.subscribe(() => refresh().catch(failed));
  refresh().catch(failed);
})();
