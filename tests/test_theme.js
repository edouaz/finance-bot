'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require.resolve('../public/theme.js'), 'utf8');

function fixture({ saved = null, dark = false, blocked = false, writeBlocked = false } = {}) {
  const writes = [];
  const attributes = {};
  const handlers = {};
  const events = {};
  const root = { dataset: {}, setAttribute(name, value) { this.dataset[name.replace('data-', '')] = value; } };
  const button = {
    setAttribute(name, value) { attributes[name] = String(value); },
    addEventListener(name, handler) { handlers[name] = handler; },
  };
  const media = {
    matches: dark,
    addEventListener(name, handler) { events[name] = handler; },
  };
  const document = {
    documentElement: root,
    getElementById(id) { assert.equal(id, 'theme-toggle'); return button; },
    addEventListener(name, handler) { events[name] = handler; },
  };
  const storage = {
    getItem(key) { assert.equal(key, 'finance-theme'); return saved; },
    setItem(key, value) {
      if (writeBlocked) throw new Error('quota exceeded');
      writes.push([key, value]);
    },
  };
  const window = {
    matchMedia(query) { assert.equal(query, '(prefers-color-scheme: dark)'); return media; },
    get localStorage() { if (blocked) throw new Error('storage blocked'); return storage; },
  };
  vm.runInNewContext(source, { window, document, matchMedia: window.matchMedia,
    get localStorage() { return window.localStorage; } });
  const initial = root.dataset.theme;
  events.DOMContentLoaded();
  return { root, attributes, writes, initial,
    click() { handlers.click(); },
    system(dark) { media.matches = dark; events.change({ matches: dark }); },
  };
}

for (const dark of [false, true]) {
  const f = fixture({ dark });
  assert.equal(f.initial, dark ? 'dark' : 'light', 'Theme is applied before DOMContentLoaded');
  assert.equal(f.attributes['aria-pressed'], String(dark));
  const label = f.attributes['aria-label'];
  assert.ok(label && label.trim());
  f.click();
  assert.equal(f.root.dataset.theme, dark ? 'light' : 'dark');
  assert.equal(f.attributes['aria-pressed'], String(!dark));
  assert.notEqual(f.attributes['aria-label'], label);
  assert.deepEqual(f.writes, [['finance-theme', dark ? 'light' : 'dark']]);
  f.system(dark);
  assert.equal(f.root.dataset.theme, dark ? 'light' : 'dark', 'Manual choice survives system changes');
}

for (const saved of ['light', 'dark']) {
  const f = fixture({ saved, dark: saved === 'light' });
  assert.equal(f.initial, saved);
  f.system(saved === 'light');
  assert.equal(f.root.dataset.theme, saved);
  assert.deepEqual(f.writes, []);
}

for (const saved of [null, '', 'DARK', 'auto', '<img src=x onerror=alert(1)>']) {
  const f = fixture({ saved });
  assert.equal(f.initial, 'light');
  f.system(true);
  assert.equal(f.root.dataset.theme, 'dark');
  assert.equal(f.attributes['aria-pressed'], 'true');
  assert.deepEqual(f.writes, []);
}

for (const options of [{ blocked: true }, { writeBlocked: true }]) {
  const f = fixture(options);
  f.click();
  assert.equal(f.root.dataset.theme, 'dark');
  assert.equal(f.attributes['aria-pressed'], 'true');
  f.system(false);
  assert.equal(f.root.dataset.theme, 'dark', 'Storage failure does not undo a manual choice');
}

console.log('Theme: initial preference, validated storage, accessible toggle, system changes and storage failures passed.');

const path = require('node:path');
const publicDir = path.resolve(__dirname, '../public');
const pages = fs.readdirSync(publicDir).filter(name => name.endsWith('.html'));
for (const name of pages) {
  const html = fs.readFileSync(path.join(publicDir, name), 'utf8');
  assert.equal((html.match(/id="theme-toggle"/g) || []).length, 1, `${name}: one theme control`);
  assert.ok(html.indexOf('src="theme.js"') < html.indexOf('href="style.css"'), `${name}: theme before paint`);
  assert.ok(!html.includes('>f.</span>'), `${name}: no old brand mark`);
  for (const match of html.matchAll(/(?:src|href)="([^"#]+\.(?:js|css|svg))"/g)) {
    assert.ok(fs.existsSync(path.join(publicDir, match[1])), `${name}: asset ${match[1]} exists`);
  }
}
const callback = fs.readFileSync(path.join(publicDir, 'callback.html'), 'utf8');
assert.ok(callback.indexOf('src="callback.js"') < callback.indexOf('src="theme.js"'), 'Callback removes URL secrets before loading theme');
console.log(`${pages.length} pages have theme controls, valid assets and early theme loading; callback priority preserved.`);
