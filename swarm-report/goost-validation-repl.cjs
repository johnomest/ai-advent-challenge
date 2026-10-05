const {chromium} = require('C:/Users/John Omest/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const staticDir = 'D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/static/';
const html = fs.readFileSync(staticDir + 'index.html', 'utf8');
const js = fs.readFileSync(staticDir + 'app.js', 'utf8');
const ids = [...html.matchAll(/id="([^"]+)"/g)].map(m => m[1]);
assert.equal(ids.length, new Set(ids).size);
assert(!js.includes('innerHTML'));
for (const filename of ['app.js', 'styles.css', 'tokens.css']) assert(fs.existsSync(staticDir + filename));
console.log('Static integrity PASS');
const scenario = 'D:/Work/Projects/ai-advent-challenge/swarm-report/goost-chat-e2e-scenario.md';
async function act(fn) {
  execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Get-Content -Raw -Encoding UTF8 "' + scenario + '"']);
  return await fn();
}
const r = require('node:repl').start({prompt:'validation> ', useGlobal:true});
Object.assign(globalThis, {chromium, fs, assert, act});
