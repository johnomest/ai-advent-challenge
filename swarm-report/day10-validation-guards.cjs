module.exports = async function ({page}, act, api, chats, assert) {
  let release, reached;
  let gate = new Promise(resolve => {release = resolve;});
  let started = new Promise(resolve => {reached = resolve;});
  const route = '**/token-preview';
  await act(() => page.route(route, async handler => {
    if (handler.request().postDataJSON().message !== 'old-preview') return handler.continue();
    const response = await handler.fetch();
    reached();
    await gate;
    await handler.fulfill({response});
  }));
  await act(() => page.locator('#message').fill('old-preview'));
  await started;
  const current = page.waitForResponse(r => r.url().endsWith('/token-preview') && r.request().postDataJSON().message.startsWith('new-preview'));
  await act(() => page.locator('#message').fill('new-preview ' + 'x'.repeat(300)));
  await current;
  const expected = await act(() => page.locator('#request-tokens').textContent());
  release();
  await act(() => page.waitForTimeout(100));
  assert.equal(await act(() => page.locator('#request-tokens').textContent()), expected);
  await act(() => page.unroute(route));

  gate = new Promise(resolve => {release = resolve;});
  started = new Promise(resolve => {reached = resolve;});
  const oldPath = '**/api/chats/' + chats.sliding_window.id;
  await act(() => page.route(oldPath, async handler => {
    const response = await handler.fetch();
    reached();
    await gate;
    await handler.fulfill({response});
  }));
  await act(() => page.locator('.chat-row').filter({has: page.locator('[data-action="' + chats.sliding_window.id + '"]')}).locator('.chat-select').click());
  await started;
  await act(() => page.locator('.chat-row').filter({has: page.locator('[data-action="' + chats.sticky_facts.id + '"]')}).locator('.chat-select').click());
  await act(() => page.waitForFunction(() => document.querySelector('#strategy').value === 'sticky_facts'));
  release();
  await act(() => page.waitForTimeout(100));
  assert.equal(await act(() => page.locator('#strategy').inputValue()), 'sticky_facts');
  assert((await act(() => page.locator('#memory-facts').textContent())).includes('Брест'));
  await act(() => page.unroute(oldPath));
  console.log('PASS stale preview and selection guards');
};
