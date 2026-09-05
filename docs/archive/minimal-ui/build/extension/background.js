// background.js - Chrome Version
// We don't handle data here anymore. The content script handles it via direct injection.

// Update listener for the browser action button (top right icon)
chrome.action.onClicked.addListener((tab) => {
    chrome.tabs.create({ url: chrome.runtime.getURL('db.html') });
});

chrome.runtime.onMessage.addListener((message) => {
    if (!message || message.type !== "openComparison") return;

    const comparisonPage = chrome.runtime.getURL("db.html");
    const comparisonUrl = comparisonPage + "#compare";

    const openNewTab = () => {
        chrome.tabs.create({ url: comparisonUrl }, () => {
            if (chrome.runtime.lastError) {
                console.error("DTU Analyzer: Could not open the comparison tab:", chrome.runtime.lastError.message);
            }
        });
    };

    const reuseTab = (context) => {
        chrome.tabs.update(context.tabId, { active: true, url: comparisonUrl }, () => {
            if (chrome.runtime.lastError) {
                // The tab can be closed between the lookup and the update
                console.warn("DTU Analyzer: Could not reuse the comparison tab:", chrome.runtime.lastError.message);
                openNewTab();
                return;
            }
            chrome.windows.update(context.windowId, { focused: true }, () => {
                if (chrome.runtime.lastError) {
                    console.warn("DTU Analyzer: Could not focus the comparison window:", chrome.runtime.lastError.message);
                }
            });
        });
    };

    // getContexts lists our own extension pages without the "tabs" permission,
    // which tabs.query would otherwise need to filter by url
    if (typeof chrome.runtime.getContexts !== "function") {
        openNewTab();
        return;
    }

    chrome.runtime.getContexts({ contextTypes: ["TAB"] }, (contexts) => {
        if (chrome.runtime.lastError) {
            console.warn("DTU Analyzer: Could not list open extension pages:", chrome.runtime.lastError.message);
            openNewTab();
            return;
        }

        const existing = (contexts || []).find((context) =>
            context.tabId > 0 && context.documentUrl && context.documentUrl.startsWith(comparisonPage)
        );
        if (!existing) {
            openNewTab();
            return;
        }
        reuseTab(existing);
    });
});
