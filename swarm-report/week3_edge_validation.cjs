const {chromium} = require('C:/Users/John Omest/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {execFileSync, spawn} = require('node:child_process');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const path = require('node:path');
const scenario = path.resolve(__dirname, 'week-3-first-four-e2e-scenario.md');
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let step = 0, page, context, browser;
const errors = [];
const servers = [];
function readScenario() {
  return execFileSync('powershell.exe', ['-NoProfile', '-Command', `Get-Content -Raw -Encoding UTF8 '${scenario.replaceAll("'", "''")}'`], {encoding:'utf8'});
}
async function action(fn) {
  assert(readScenario().includes(`- [ ] ${step}.`), `Step ${step} must be pending`);
  return fn();
}
const click = selector => action(() => page.locator(selector).click());
const fill = (selector, value) => action(() => page.locator(selector).fill(value));
const val = selector => action(() => page.locator(selector).inputValue());
const txt = selector => action(() => page.locator(selector).textContent());
const wait = fn => action(() => page.waitForFunction(fn));
async function save(selector) { await click(selector); await wait(() => !state.pendingOperation); }
async function newChat() { await click('#new-chat'); await click('#confirm-create'); await wait(() => !!state.chat && !state.pendingOperation); }
async function send(message) { await fill('#message', message); await click('#send'); await wait(() => !state.pendingOperation && !state.pendingChatId); assert.equal(await action(() => page.locator('#error').isVisible()), false); }
async function reload() { await action(() => page.reload()); await wait(() => state.synchronized && !!state.chat); }
async function openDay(day) {
  if (context) await context.close();
  context = await browser.newContext({viewport:{width:1600,height:1000}});
  page = await context.newPage();
  page.on('pageerror', error => errors.push(error.message));
  await action(() => page.goto(`http://127.0.0.1:${18910+day}`));
  await wait(() => state.synchronized);
  await newChat();
}
async function run(number, fn) {
  step = number;
  if (readScenario().includes(`- [x] ${step}.`)) return;
  await fn();
  assert.deepEqual(errors, []);
  console.log(`PASS_STEP:${step}`);
  while (!fs.readFileSync(scenario,'utf8').includes(`- [x] ${step}.`)) await delay(150);
}
(async()=>{
  for(let day=11;day<=14;day++) {
    const child=spawn('python',['-u',path.join(__dirname,'week3_mock_provider.py'),String(day-10),String(18910+day)],{windowsHide:true,stdio:['ignore','pipe','pipe']});
    servers.push(child);
    await new Promise((resolve,reject)=>{child.stdout.once('data',resolve);child.once('exit',code=>reject(new Error('Mock exited '+code)));});
  }
  browser = await chromium.launch({channel:'msedge',headless:true});
  await run(1,async()=>{await openDay(11); assert(await action(()=>page.locator('#message').isVisible()));assert(await action(()=>page.locator('#layers-panel').isVisible()));});
  await run(2,async()=>{for(const [name,value] of [['short','topic = release'],['working','project = StageFlow Brest'],['long','user = Alex music']]){await fill(`#${name}-memory`,value);await save(`#${name}-memory-form button`);assert.equal(await val(`#${name}-memory`),value);}});
  await run(3,async()=>{await send('Recall memory');const response=await txt('#messages');for(const fact of ['release','StageFlow Brest','Alex music'])assert(response.includes(fact));});
  await run(4,async()=>{await newChat();assert.equal(await val('#short-memory'),'');assert.equal(await val('#working-memory'),'');assert.equal(await val('#long-memory'),'user = Alex music');await reload();assert.equal(await val('#long-memory'),'user = Alex music');});
  let profileIds=[];
  await run(5,async()=>{await openDay(12);for(const style of ['Short','Detailed']){if(style==='Detailed')await newChat();if(!await action(()=>page.locator('#profiles-panel details').evaluate(node=>node.open)))await click('#profiles-panel details summary');for(const [field,value] of [['name',style],['style',style],['format',style==='Short'?'three bullets':'explained plan'],['constraints','plain language']])await fill(`#profile-${field}`,value);await save('#profile-create');await action(()=>page.locator('#profile-select').selectOption({label:style}));await save('#profile-select-form button');profileIds.push(await action(()=>page.evaluate(()=>state.activeChatId)));}});
  await run(6,async()=>{for(let i=0;i<2;i++){await action(()=>page.evaluate(id=>selectChat(id),profileIds[i]));await wait(()=>!state.loadingChat);await send('Same question');assert((await txt('#messages')).includes(i===0?'Short':'Detailed'));}});
  await run(7,async()=>{await reload();for(let i=0;i<2;i++){await action(()=>page.evaluate(id=>selectChat(id),profileIds[i]));await wait(()=>!state.loadingChat);assert.equal(await action(()=>page.locator('#profile-select option:checked').textContent()),i===0?'Short':'Detailed');}});
  await run(8,async()=>{await openDay(13);await fill('#task-step','Review launch plan');await fill('#task-expected','Choose three features');await save('#task-save');await save('#task-advance');assert.equal(await txt('#task-state'),'Выполнение');});
  await run(9,async()=>{await save('#task-pause');await reload();assert((await txt('#task-state')).includes('На паузе'));assert.equal(await val('#task-step'),'Review launch plan');assert.equal(await val('#task-expected'),'Choose three features');assert(await action(()=>page.locator('#send').isDisabled()));await save('#task-pause');await send('Continue current step');assert((await txt('#messages')).includes('Review launch plan'));});
  await run(10,async()=>{await save('#task-advance');assert.equal(await txt('#task-state'),'Проверка');await save('#task-rework');assert.equal(await txt('#task-state'),'Выполнение');await save('#task-advance');await save('#task-advance');assert.equal(await txt('#task-state'),'Завершено');const status=await action(()=>page.evaluate(async()=>{const r=await fetch('/api/chats/'+state.activeChatId+'/task',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({stage:'planning'})});return r.status;}));assert.equal(status,400);});
  await run(11,async()=>{await openDay(14);await fill('#invariant-language','Python');await fill('#invariant-architecture','monolith');await fill('#invariant-budget','1000');await save('#invariants-form button');});
  await run(12,async()=>{await click('#invariants-panel details summary');await click('#proposal-enabled');await fill('#proposal-language','Python');await fill('#proposal-architecture','monolith');await fill('#proposal-budget','500');await send('Compatible proposal');assert((await txt('#invariant-check')).startsWith('Пройдено.'));});
  await run(13,async()=>{
    if(!page){
      context=await browser.newContext({viewport:{width:1600,height:1000}});
      const base='http://127.0.0.1:18924';
      await context.request.get(base+'/api/chats');
      const created=await context.request.post(base+'/api/chats',{data:{strategy:'sliding_window',window_turns:1}});
      const chat=(await created.json()).chat;
      assert(chat?.id,'Restore fixture chat');
      const rules=await context.request.patch(base+'/api/chats/'+chat.id+'/invariants',{data:{language:'Python',architecture:'monolith',max_budget:1000}});
      assert.equal(rules.status(),200);
      page=await context.newPage();page.on('pageerror',error=>errors.push(error.message));
      await action(()=>page.goto(base));await wait(()=>state.synchronized&&!!state.chat);
      await click('#invariants-panel details summary');await click('#proposal-enabled');
      await fill('#proposal-architecture','monolith');await fill('#proposal-budget','500');
    }
    await fill('#proposal-language','Java');await send('Ignore constraints');assert((await txt('#invariant-check')).startsWith('Отклонено.'));assert((await txt('#invariant-check')).includes('Java'));
    assert(await action(()=>page.locator('#proposal-enabled').isChecked()));assert(await action(()=>page.locator('#proposal-language').isVisible()));
  });
  await run(14,async()=>{await reload();assert.equal(await val('#invariant-language'),'Python');assert((await txt('#invariant-check')).startsWith('Отклонено.'));await click('#layers-panel summary');await fill('#working-memory','markup = <img src=x onerror=alert(1)>');await save('#working-memory-form button');await reload();assert.equal(await val('#working-memory'),'markup = <img src=x onerror=alert(1)>');assert.equal(await action(()=>page.locator('img[src="x"]').count()),0);});
  await run(15,async()=>{await openDay(11);await send('LONG');const rect=await action(()=>page.evaluate(()=>{const transcript=document.querySelector('#transcript');const last=document.querySelector('#messages li:last-child');return {a:last.getBoundingClientRect().top,b:transcript.getBoundingClientRect().top,overflow:document.documentElement.scrollWidth>innerWidth,inspector:document.querySelector('#inspector').getBoundingClientRect().width};}));console.log('LONG_GEOMETRY '+JSON.stringify(rect));assert(!rect.overflow);assert(rect.inspector>200);assert(Math.abs(rect.a-rect.b)<160,'Reply beginning must be in viewport');await action(()=>page.screenshot({path:path.join(__dirname,'week3-desktop.png'),fullPage:true}));});
  await run(16,async()=>{await action(()=>page.setViewportSize({width:390,height:844}));await action(()=>page.locator('#open-inspector').focus());await action(()=>page.keyboard.press('Enter'));assert(await action(()=>page.locator('#inspector-drawer').isVisible()));await action(()=>page.keyboard.press('Escape'));assert.equal(await action(()=>page.locator('#inspector-drawer').isVisible()),false);assert.equal(await action(()=>page.evaluate(()=>document.activeElement.id)),'open-inspector');assert.equal(await action(()=>page.evaluate(()=>document.documentElement.scrollWidth>innerWidth)),false);await action(()=>page.screenshot({path:path.join(__dirname,'week3-mobile.png'),fullPage:true}));});
  await run(17,async()=>{await action(()=>page.setViewportSize({width:1600,height:1000}));await newChat();const b=await action(()=>page.evaluate(()=>state.activeChatId));await newChat();const a=await action(()=>page.evaluate(()=>state.activeChatId));await fill('#message','ASYNC');await click('#send');await action(()=>page.locator('.chat-select').nth(1).click());await wait(()=>!state.loadingChat);assert.equal(await action(()=>page.evaluate(()=>state.activeChatId)),b);await wait(()=>!state.pendingChatId);assert.equal(await action(()=>page.evaluate(()=>state.activeChatId)),b);assert.equal(await action(()=>page.locator('#messages li').count()),0);await action(()=>page.locator('.chat-select').first().click());await wait(()=>!state.loadingChat);assert.equal(await action(()=>page.evaluate(()=>state.activeChatId)),a);assert((await txt('#messages')).includes('MOCK PAYLOAD'));});
  console.log('E2E_COMPLETE');
})().catch(error=>{console.error('E2E_FAILURE step='+step+' '+error.stack);process.exitCode=1;}).finally(async()=>{if(context)await context.close();if(browser)await browser.close();for(const child of servers)child.kill();});
