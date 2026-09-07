const assert = require('node:assert/strict');
const test = require('node:test');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function worker({ failFirstWrite = false } = {}) {
  const listeners = [];
  let stored = [];
  let failed = false;
  const chrome = {
    action: { onClicked: { addListener() {} } },
    runtime: { onMessage: { addListener(fn) { listeners.push(fn); } } },
    storage: { local: {
      get(key, callback) { setImmediate(() => callback({ [key]: stored.slice() })); },
      set(items, callback) {
        setImmediate(() => {
          if (failFirstWrite && !failed) {
            failed = true;
            chrome.runtime.lastError = { message: 'storage unavailable' };
          } else {
            stored = Object.values(items)[0];
          }
          callback();
          delete chrome.runtime.lastError;
        });
      },
    } },
  };
  const context = vm.createContext({ chrome, console });
  context.importScripts = (file) => vm.runInContext(
    fs.readFileSync(path.join(__dirname, '../extension', file), 'utf8'), context
  );
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../extension/background.js'), 'utf8'), context);
  const send = (action, courseId) => new Promise(resolve => {
    assert.equal(listeners[0]({ type: 'updateComparison', action, courseId }, {},
      result => resolve(JSON.parse(JSON.stringify(result)))), true);
  });
  return { send, stored: () => Array.from(stored) };
}

test('concurrent adds from separate tabs preserve both selections', async () => {
  const w = worker();
  await Promise.all([w.send('toggle', '01001'), w.send('toggle', '01911')]);
  assert.deepEqual(w.stored(), ['01001', '01911']);
});

test('queued changes enforce the limit and order clears with toggles', async () => {
  const w = worker();
  const results = await Promise.all(['01001', '01911', '02443', '42500', '42504']
    .map(id => w.send('toggle', id)));
  assert.equal(results[4].limitReached, true);
  assert.equal(w.stored().length, 4);
  await Promise.all([w.send('clear'), w.send('toggle', '42504')]);
  assert.deepEqual(w.stored(), ['42504']);
});

test('a failed write does not block later queued operations', async () => {
  const w = worker({ failFirstWrite: true });
  const results = await Promise.all([w.send('toggle', '01001'), w.send('toggle', '01911')]);
  assert.match(results[0].error, /storage unavailable/);
  assert.deepEqual(w.stored(), ['01911']);
});
