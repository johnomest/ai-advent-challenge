const {chromium} = require('C:/Users/John Omest/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {execFileSync, spawn} = require('node:child_process');
const assert = require('node:assert/strict');
const scenario = 'D:/Work/Projects/ai-advent-challenge/swarm-report/day10-sidebar-e2e-scenario.md';
async function act(fn) {
  execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Get-Content -Raw -Encoding UTF8 "' + scenario + '"']);
  return await fn();
}
let browser, context, page, origin, server, width;
const errors = [];
async function start(w=1440,h=1000) {
  server = spawn('python', ['swarm-report/day10-validation-server.py'], {stdio:['pipe','pipe','pipe']});
  server.stderr.on('data', b => process.stderr.write(b));
  const port = await new Promise((resolve, reject) => {server.stdout.once('data', b => resolve(JSON.parse(b.toString()).port)); server.once('error', reject);});
  origin = 'http://127.0.0.1:' + port;
  browser = await act(() => chromium.launch({channel:'msedge', headless:true}));
  await setup(w, h);
}
async function setup(w,h) {
  if(context) await act(() => context.close());
  width=w;
  context = await act(() => browser.newContext({viewport:{width:w,height:h}, reducedMotion:'reduce'}));
  page = await act(() => context.newPage());
  page.on('pageerror', e => errors.push(e.message));
  await act(() => page.goto(origin));
  await ready();
}
async function ready() {await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));}
async function click(id) {await act(() => page.locator(id).click());}
async function inspector() {if(width<1280) await click('#open-inspector');}
async function closeInspector() {if(width<1280) await click('#close-inspector');}
async function create(strategy='sliding_window') {
  if(width<960) await click('#open-drawer');
  await click('#new-chat');
  await act(() => page.locator('#new-strategy').selectOption(strategy));
  await click('#confirm-create');
  await ready();
}
async function layout() {
  const data = await act(() => page.evaluate(() => {
    const $ = id => document.getElementById(id), box = id => {const r=$(id).getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}};
    return {width:innerWidth,scroll:document.documentElement.scrollWidth,workspace:box('workspace'),inspector:box('inspector'),sidebar:box('sidebar'),technical:['model','sync','stats','status','memory-panel','strategy','branch-form','token-preview','token-details'].every(id => $('inspector').contains($(id))),center:!$('workspace').querySelector('#model,#sync,#stats,#status,#memory-panel,#token-preview,#token-details'),host:$('inspector').parentElement.id};
  }));
  assert(data.technical && data.center, JSON.stringify(data)); assert(data.scroll<=data.width,JSON.stringify(data));
  assert.equal(data.host,width>=1280?'inspector-host':'inspector-drawer');
  if(width>=1280) assert(data.inspector.x>=data.workspace.x+data.workspace.w-1);
  console.log('PASS layout', JSON.stringify(data));
}
async function anchor(selector) {
  const result = await act(() => page.locator(selector).last().evaluate(el => {const t=document.querySelector('#transcript');const c=getComputedStyle(el);return {top:el.getBoundingClientRect().top-t.getBoundingClientRect().top,height:el.offsetHeight,view:t.clientHeight,bg:c.backgroundColor,author:el.querySelector('.message-author').textContent,scroll:t.scrollTop};}));
  assert(Math.abs(result.top-16)<1.2,JSON.stringify(result));
  assert(result.bg!=='rgba(0, 0, 0, 0)'); assert(result.author); console.log('PASS anchor',selector,result); return result;
}
const longText = 'Начало длинного сообщения.\n' + 'Строка текста для проверки прокрутки.\n'.repeat(85) + 'Конец длинного сообщения.';
async function send(text) {
  let release, entered; const gate=new Promise(r=>release=r), requestEntered=new Promise(r=>entered=r);
  await act(() => page.route('**/messages', async route=>{entered();await gate;await route.continue();}, {times:1}));
  await act(() => page.locator('#message').fill(text));
  await click('#send'); await requestEntered;
  await anchor('.message[data-pending]');
  release(); await ready(); await anchor('.message.assistant');
  assert.equal(await act(()=>page.locator('[data-pending]').count()),0);
}
async function screenshot(name) {await act(()=>page.screenshot({path:'swarm-report/day10-sidebar-'+name+'.png',fullPage:true}));}
async function syncPreserves() {
  await act(()=>page.locator('#transcript').evaluate(el=>el.scrollTop=85));
  const before=await act(()=>page.locator('#transcript').evaluate(el=>el.scrollTop));
  await act(()=>page.locator('#message').fill('Черновик проверки'));
  await act(()=>page.waitForFunction(()=>/Осталось|Лимит превышен/.test(document.querySelector('#preview-status').textContent)));
  assert.equal(await act(()=>page.locator('#transcript').evaluate(el=>el.scrollTop)),before);
  await inspector(); await click('#sync'); await ready(); await closeInspector();
  assert.equal(await act(()=>page.locator('#transcript').evaluate(el=>el.scrollTop)),before);
  console.log('PASS preview/sync preserve',before);
}
async function finish() {assert.deepEqual(errors,[]); if(context)await act(()=>context.close());if(browser)await act(()=>browser.close());server.stdin.end('stop\n');console.log('PASS no pageerrors; browser closed; server stop sent');}
Object.assign(globalThis,{start,setup,act,ready,click,inspector,closeInspector,create,layout,anchor,send,longText,screenshot,syncPreserves,finish,errors,assert,runtime:()=>({page,context,browser,origin,width}),setWidth:w=>width=w});
require('node:repl').start({prompt:'sidebar> ',useGlobal:true});
