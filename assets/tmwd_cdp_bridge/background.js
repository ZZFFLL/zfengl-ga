// background.js - Cookie + CDP Bridge
chrome.runtime.onInstalled.addListener(() => console.log('CDP Bridge installed'));

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.action === 'getCookies') {
    handleGetCookies(msg, sender).then(sendResponse);
    return true;
  }
  if (msg.action === 'cdp') {
    handleCDP(msg, sender).then(sendResponse);
    return true;
  }
});

async function handleGetCookies(msg, sender) {
  try {
    const url = msg.url || sender.tab?.url;
    const origin = url.match(/^https?:\/\/[^\/]+/)[0];
    const all = await chrome.cookies.getAll({ url });
    const part = await chrome.cookies.getAll({ url, partitionKey: { topLevelSite: origin } }).catch(() => []);
    const merged = [...all];
    for (const c of part) {
      if (!merged.some(x => x.name === c.name && x.domain === c.domain)) merged.push(c);
    }
    return { ok: true, data: merged };
  } catch (e) {
    return { ok: false, error: e.message };
  }
}

async function handleCDP(msg, sender) {
  const tabId = msg.tabId || sender.tab?.id;
  if (!tabId) return { ok: false, error: 'no tabId' };
  try {
    await chrome.debugger.attach({ tabId }, '1.3');
    const result = await chrome.debugger.sendCommand({ tabId }, msg.method, msg.params || {});
    await chrome.debugger.detach({ tabId });
    return { ok: true, data: result };
  } catch (e) {
    try { await chrome.debugger.detach({ tabId }); } catch (_) {}
    return { ok: false, error: e.message };
  }
}