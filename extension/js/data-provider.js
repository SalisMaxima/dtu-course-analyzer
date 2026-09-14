// Every view receives one authenticated dataset generation from the background.
(function (root) {
  function message(type, fields = {}) {
    return new Promise((resolve, reject) => chrome.runtime.sendMessage({ type, ...fields }, result => {
      const error = chrome.runtime.lastError;
      if (error || !result || result.error) reject(new Error(error ? error.message : result && result.error || "Data provider unavailable"));
      else resolve(result);
    }));
  }
  function status(view) {
    const date = view.metadata && view.metadata.collected_at;
    const source = view.source === "bundled" ? "Bundled data" : view.source === "last-known-good" ? "Previous verified data" : "Verified release " + view.generation;
    const age = date ? " · collected " + date.slice(0, 10) : " · collection date unavailable";
    return source + age + (view.state && view.state.error ? " · update unavailable" : "");
  }
  root.DTUData = {
    read: courseId => message("courseDataGet", courseId ? { courseId } : {}),
    message, status,
    subscribe: fn => chrome.runtime.onMessage.addListener(message => {
      if (message && message.type === "courseDataChanged") fn();
    })
  };
})(globalThis);
