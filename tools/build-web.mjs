import { access, readFile } from 'node:fs/promises';
import { constants } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const required = [
  'frontend/index.html',
  'frontend/app.js',
  'frontend/styles.css',
  'frontend/runtime-config.js',
  'frontend/sw.js',
  'frontend/manifest.webmanifest',
  'backend/app/main.py',
  'desktop/main.cjs'
];
for (const relative of required) {
  try { await access(path.join(root, relative), constants.R_OK); }
  catch { throw new Error('Required app asset is missing: ' + relative); }
}
const html = await readFile(path.join(root, 'frontend/index.html'), 'utf8');
for (const asset of ['styles.css', 'manifest.webmanifest', 'app.js', "navigator.serviceWorker.register('/sw.js')"]) {
  if (!html.includes(asset)) throw new Error('frontend/index.html does not reference ' + asset);
}
console.log('Required web assets are present. Using the recovered prebuilt browser bundle frontend/app.js.');
