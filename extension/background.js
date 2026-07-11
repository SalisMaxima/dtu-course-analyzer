// background.js - Chrome Version
// We don't handle data here anymore. The content script handles it via direct injection.

// Update listener for the browser action button (top right icon)
chrome.action.onClicked.addListener((tab) => {
    chrome.tabs.create({ url: chrome.runtime.getURL('db.html') });
});

chrome.runtime.onMessage.addListener((message) => {
    if (!message || message.type !== "openComparison") return;

    const comparisonUrl = chrome.runtime.getURL("db.html#compare");
    chrome.tabs.query({ url: chrome.runtime.getURL("db.html*") }, (tabs) => {
        if (tabs && tabs.length > 0) {
            chrome.tabs.update(tabs[0].id, { active: true, url: comparisonUrl });
            return;
        }
        chrome.tabs.create({ url: comparisonUrl });
    });
});
