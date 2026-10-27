'use strict';
const assert = require('node:assert/strict');
const { serverOrigin, setupConnection, SERVER_KEY } = require('../public/connection.js');

for (const [value, expected] of [
  ['https://finance.example', 'https://finance.example'],
  ['https://finance.example/', 'https://finance.example'],
  ['https://finance.example:8443', 'https://finance.example:8443'],
  ['https://FINANCE.example:443/', 'https://finance.example'],
]) assert.equal(serverOrigin(value), expected);

const malicious = [
  '', null, undefined, {}, 'http://finance.example', 'javascript:alert(1)',
  '//finance.example', 'https://', ' https://finance.example', 'https://finance.example ',
  'https://finance.example\n', 'https://finance.example\t.evil.example',
  'https://finance.example/callback', 'https://finance.example/?code=secret&state=secret',
  'https://finance.example?', 'https://finance.example#', 'https://finance.example/#secret',
  'https://finance.example/..', 'https://finance.example/%2e',
  'https://finance.example\\@evil.example', 'https://finance.example//',
  'https://finance:password@finance.example', 'https://finance.example@evil.example',
  'https://finance.example:invalid', 'https://finance.example/<img src=x onerror=alert(1)>',
  'https://finance.example" onclick="alert(1)',
];
for (const value of malicious) assert.throws(() => serverOrigin(value), String(value));

function fixture(saved = null, blocked = false) {
  const data = new Map(saved === null ? [] : [[SERVER_KEY, saved]]);
  const writes = [];
  const navigation = [];
  const elements = Object.fromEntries(['server', 'status', 'open', 'forget'].map(id => [id, {
    value: '', textContent: '', disabled: false, handlers: {},
    addEventListener(type, handler) { this.handlers[type] = handler; },
    set innerHTML(_) { assert.fail('Untrusted data must never be interpreted as HTML'); },
  }]));
  const browser = {
    get localStorage() {
      if (blocked) throw new Error('storage blocked');
      return {
        getItem: key => data.has(key) ? data.get(key) : null,
        setItem(key, value) { writes.push([key, value]); data.set(key, value); },
        removeItem: key => data.delete(key),
      };
    },
    location: { assign: value => navigation.push(value) },
  };
  setupConnection({ getElementById: id => elements[id] }, browser);
  return { elements, browser, data, writes, navigation };
}

// Saved configuration never navigates without a fresh, explicit click.
{
  const f = fixture('https://finance.example/');
  assert.equal(f.elements.server.value, 'https://finance.example');
  assert.equal(f.elements.open.disabled, false);
  assert.deepEqual(f.navigation, []);
  assert.deepEqual(f.writes, []);
  f.elements.open.handlers.click();
  assert.deepEqual(f.writes, [[SERVER_KEY, 'https://finance.example']]);
  assert.deepEqual(f.navigation, ['https://finance.example/']);
}

// Tampered stored values are validated before use, removed, and never rendered as HTML.
for (const saved of malicious) {
  if (saved === null) continue;
  const f = fixture(saved);
  assert.equal(f.elements.server.value, '');
  assert.equal(f.elements.open.disabled, true);
  assert.equal(f.data.has(SERVER_KEY), false);
  assert.deepEqual(f.navigation, []);
}

// Revalidate on confirmation even when the input event was bypassed.
{
  const f = fixture('https://finance.example');
  f.elements.server.value = 'https://evil.example/?code=secret';
  f.elements.open.handlers.click();
  assert.deepEqual(f.navigation, []);
  assert.deepEqual(f.writes, []);
  assert.equal(f.elements.open.disabled, true);
  assert.ok(!f.elements.status.textContent.includes('secret'));
}

// Storage blocked by browser privacy policy does not prevent private-server navigation.
{
  const f = fixture(null, true);
  assert.match(f.elements.status.textContent, /storage is blocked/);
  f.elements.server.value = 'https://finance.example';
  f.elements.server.handlers.input();
  assert.equal(f.elements.open.disabled, false);
  f.elements.open.handlers.click();
  assert.deepEqual(f.navigation, ['https://finance.example/']);
  f.elements.forget.handlers.click();
  assert.equal(f.elements.server.value, '');
  assert.equal(f.elements.open.disabled, true);
  assert.match(f.elements.status.textContent, /storage removal is blocked/);
}

// Forget clears the only stored item and disables navigation.
{
  const f = fixture('https://finance.example');
  f.elements.forget.handlers.click();
  assert.equal(f.data.has(SERVER_KEY), false);
  assert.equal(f.elements.server.value, '');
  assert.equal(f.elements.open.disabled, true);
  assert.deepEqual(f.navigation, []);
}

// A storage write failure still opens the validated origin, without retaining secrets.
{
  const f = fixture();
  Object.defineProperty(f.browser, 'localStorage', {
    get() { return { setItem() { throw new Error('quota exceeded'); } }; },
  });
  f.elements.server.value = 'https://finance.example';
  f.elements.open.handlers.click();
  assert.deepEqual(f.navigation, ['https://finance.example/']);
  assert.deepEqual(f.writes, []);
}

console.log('Connection page: URL validation, confirmation, tampered storage, blocked storage and text-only rendering passed.');
