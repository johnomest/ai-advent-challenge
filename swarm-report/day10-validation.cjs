const {chromium, expect} = require('C:/Users/John Omest/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const {execFileSync} = require('node:child_process');
const assert = require('node:assert/strict');
const scenario = 'D:/Work/Projects/ai-advent-challenge/swarm-report/day10-context-strategies-e2e-scenario.md';
async function act(fn) {
  execFileSync('powershell.exe', ['-NoProfile', '-Command', 'Get-Content -Raw -Encoding UTF8 "' + scenario + '"']);
  return await fn();
}
const messages = ['Меня зовут Анна. Город: Минск.', 'Язык проекта: Python.', 'Бюджет: 1000.', 'Предложи первый этап.', 'Обсудим проверку данных.', 'Добавь критерий готовности.', 'Напомни ограничения.', 'Разберём документацию.', 'Исправление: город теперь Брест.', 'Метка: <img src=x onerror=alert(1)>.', 'Сравни последние решения.', 'Назови имя, город, язык и бюджет.'];
let browser, context, page, origin, mobile = false;
const errors = [], chats = {};
async function start(port) {
  origin = 'http://127.0.0.1:' + port;
  browser = await act(() => chromium.launch({channel: 'msedge', headless: true}));
  await setup(false);
}
async function setup(isMobile) {
  if (context) await act(() => context.close());
  mobile = isMobile;
  context = await act(() => browser.newContext({viewport: mobile ? {width: 390, height: 844} : {width: 1440, height: 1000}}));
  page = await act(() => context.newPage());
  page.on('pageerror', error => errors.push(error.message));
  await act(() => page.goto(origin));
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
}
async function api(path, method = 'GET', data) {
  return await act(async () => {
    const response = await context.request.fetch(origin + path, {method, data, headers: {Origin: origin}});
    return {status: response.status(), body: await response.json()};
  });
}
async function create(strategy) {
  if (mobile) await act(() => page.locator('#open-drawer').click());
  await act(() => page.locator('#new-chat').click());
  await act(() => page.locator('#new-strategy').selectOption(strategy));
  await act(() => page.locator('#new-window-turns').fill('2'));
  const response = page.waitForResponse(r => r.url().endsWith('/api/chats') && r.request().method() === 'POST');
  await act(() => page.locator('#confirm-create').click());
  const result = await (await response).json();
  assert(result.chat, JSON.stringify(result));
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
  chats[strategy] = result.chat;
  return result.chat;
}
async function send(message) {
  await act(() => page.locator('#message').fill(message));
  const response = page.waitForResponse(r => /\/messages$/.test(r.url()) && r.request().method() === 'POST');
  await act(() => page.locator('#send').click());
  const result = await (await response).json();
  assert(result.chat, JSON.stringify(result));
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
  return result.chat;
}
async function verifyStrategy(strategy) {
  let chat = await create(strategy);
  for (const [index, message] of messages.entries()) {
    chat = await send(message);
    assert.equal(chat.messages.length, (index + 1) * 2);
  }
  chats[strategy] = chat;
  const preview = (await api('/api/chats/' + chat.id + '/token-preview', 'POST', {message: 'Проверка'})).body.estimate;
  assert.equal(preview.selected_turns, strategy === 'branching' ? 12 : 2);
  assert.equal(preview.total_turns, 12);
  assert.equal(preview.total_turns - preview.selected_turns, strategy === 'branching' ? 0 : 10);
  assert(await act(() => page.locator('#strategy').isDisabled()));
  assert.equal((await api('/api/chats/' + chat.id, 'PATCH', {strategy: 'branching'})).status, 409);
  if (!await act(() => page.locator('.memory-details').evaluate(element => element.open))) await act(() => page.locator('.memory-details summary').click());
  const text = await act(() => page.locator('#memory-context').textContent());
  assert(text.includes((strategy === 'branching' ? '12' : '2') + ' из 12'));
  if (strategy === 'sticky_facts') {
    assert.deepEqual(chat.facts, {name: 'Анна', city: 'Брест', language: 'Python', budget: '1000', label: '<img src=x onerror=alert(1)>'});
    assert.equal(chat.total_tokens, 2880);
    assert(chat.turn_metrics.every(m => m.facts_usage.total_tokens === 120 && Object.hasOwn(m, 'facts_cost') && Object.hasOwn(m, 'cost')));
    assert((await act(() => page.locator('#memory-facts').textContent())).includes('<img src=x onerror=alert(1)>'));
    assert.equal(await act(() => page.locator('#memory-facts img, #messages img').count()), 0);
  }
  await noOverflow();
  console.log('PASS strategy', mobile ? 'mobile' : 'desktop', strategy);
}
async function noOverflow() {
  const sizes = await act(() => page.evaluate(() => ({scroll: document.documentElement.scrollWidth, width: innerWidth})));
  assert(sizes.scroll <= sizes.width, JSON.stringify(sizes));
}
async function select(title) {
  if (mobile) await act(() => page.locator('#open-drawer').click());
  await act(() => page.locator('.chat-select').filter({has: page.locator('span', {hasText: title})}).first().click());
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
}
async function branch() {
  const parent = chats.branching;
  const response = page.waitForResponse(r => r.url().endsWith('/branches'));
  await act(() => page.locator('[data-checkpoint="6"]').click());
  const res = await response, payload = res.request().postDataJSON(), result = await res.json();
  assert.equal(result.branches.length, 2);
  const [a, b] = result.branches;
  assert.deepEqual(a.messages, b.messages);
  assert.deepEqual(a.messages, parent.messages.slice(0, 12));
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
  let updatedA = await send('Независимый путь A');
  assert.equal(updatedA.id, a.id);
  await select(b.title);
  let updatedB = await send('Независимый путь B');
  assert.equal(updatedB.id, b.id);
  assert(!updatedB.messages.some(m => m.content.includes('Независимый путь A')));
  await act(() => page.reload());
  await act(() => page.waitForFunction(() => !document.querySelector('#send').disabled));
  await select(a.title);
  assert(!(await act(() => page.locator('#messages').textContent())).includes('Независимый путь B'));
  assert((await act(() => page.locator('#branch-lineage').textContent())).includes('6'));
  assert.deepEqual((await api('/api/chats/' + parent.id)).body.chat.messages, parent.messages);
  assert.deepEqual((await api('/api/chats/' + parent.id + '/branches', 'POST', payload)).body, result);
  assert.equal((await api('/api/chats/' + parent.id + '/branches', 'POST', {...payload, checkpoint_turn: 5})).status, 409);
  const alien = await act(() => browser.newContext());
  try {
    await act(() => alien.request.get(origin + '/api/chats'));
    const denied = await act(() => alien.request.post(origin + '/api/chats/' + parent.id + '/branches', {data: payload, headers: {Origin: origin}}));
    assert.equal(denied.status(), 404);
  } finally {await act(() => alien.close());}
  console.log('PASS branches', mobile ? 'mobile' : 'desktop');
}
async function screenshot(name) {await noOverflow(); await act(() => page.screenshot({path: 'D:/Work/Projects/ai-advent-challenge/swarm-report/day10-' + name + '.png', fullPage: true}));}
async function finish() {assert.deepEqual(errors, []); await act(() => context.close()); await act(() => browser.close()); console.log('PASS cleanup, no page errors');}
Object.assign(globalThis, {start, setup, verifyStrategy, branch, screenshot, finish, act, api, chats, errors, select, runtime: () => ({page, context, browser}), assert});
require('node:repl').start({prompt: 'day10> ', useGlobal: true});
