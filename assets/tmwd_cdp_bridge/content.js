// content.js - DOM trigger bridge
const TID = '__ljq_ctrl';

new MutationObserver(muts => {
  for (const m of muts) for (const n of m.addedNodes) {
    if (n.id === TID || (n.querySelector && n.querySelector('#' + TID))) {
      const el = n.id === TID ? n : n.querySelector('#' + TID);
      handle(el);
    }
  }
}).observe(document.documentElement, { childList: true, subtree: true });

async function handle(el) {
  try {
    const cmd = el.dataset.cmd || 'cookies';
    let resp;
    if (cmd === 'cookies') {
      resp = await chrome.runtime.sendMessage({ action: 'getCookies', url: location.href });
    } else if (cmd === 'cdp') {
      const method = el.dataset.method;
      const params = el.dataset.params ? JSON.parse(el.dataset.params) : {};
      const tabId = el.dataset.tabid ? parseInt(el.dataset.tabid) : undefined;
      resp = await chrome.runtime.sendMessage({ action: 'cdp', method, params, tabId });
    } else {
      resp = { ok: false, error: 'unknown cmd: ' + cmd };
    }
    el.textContent = JSON.stringify(resp);
  } catch (e) {
    el.textContent = JSON.stringify({ ok: false, error: e.message });
  }
}