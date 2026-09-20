"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function run() {
  const elements = {
    "week-error": {}, "week-status": {},
    "proposal-enabled": {checked: true}, "proposal-language": {value: "Python"},
    "proposal-architecture": {value: "Monolith"}, "proposal-budget": {value: "0"},
  };
  const state = {activeChatId: "a", chat: {id: "a"}, synchronized: true, selectionVersion: 1};
  let resolveRequest;
  const rendered = [];
  const context = vm.createContext({document: {body: {dataset: {day: "14"}}}, elements, state,
    updateControls() {}, upsertChat() {}, renderChat(chat) { rendered.push(chat); },
    request() { return new Promise((resolve) => { resolveRequest = resolve; }); },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "week.js"), "utf8") +
    "\nglobalThis.api = {parseMemory, readProposal, mutateWeek};", context);
  const {parseMemory, readProposal, mutateWeek} = context.api;
  assert.equal(parseMemory("goal = a=b").goal, "a=b");
  assert.equal(Object.getPrototypeOf(parseMemory("__proto__ = plain data")), null);
  assert.equal(Object.keys(parseMemory("  \n")).length, 0);
  assert.throws(() => parseMemory("goal = a\ngoal = b"), /повторяется/);
  assert.throws(() => parseMemory("missing separator"), /ключ = значение/);
  assert.throws(() => parseMemory(Array.from({length: 13}, (_, i) => `key${i} = value`).join("\n")), /12/);
  assert.equal(readProposal().budget, 0);
  elements["proposal-budget"].value = "1.5";
  assert.throws(readProposal, /целый бюджет/);
  elements["proposal-enabled"].checked = false;
  assert.equal(readProposal(), null);

  const pending = mutateWeek("/api/chats/a/memory", "PATCH", {}, "Saved");
  assert.equal(state.pendingOperation, "week");
  state.activeChatId = "b";
  state.chat = {id: "b"};
  resolveRequest({chat: {id: "a"}});
  await pending;
  assert.equal(rendered.length, 0, "Late mutation must not replace another chat");
  assert.equal(state.pendingOperation, null);
  assert.equal(state.chat.id, "b");
  // Exercise the actual acknowledgement/recovery functions without starting the DOM app.
  const appSource = fs.readFileSync(path.join(__dirname, "app.js"), "utf8");
  Object.assign(context, {
    resetValidation() {}, setError() {}, setStatus() {}, chatPath(id) { return "/api/chats/" + id; },
  });
  vm.runInContext(appSource.slice(appSource.indexOf("function acknowledgeSend("), appSource.indexOf("function handleSendError(")) +
    "globalThis.sendApi = {acknowledgeSend, recoverSend};", context);
  Object.assign(state, {activeChatId: "a", chat: {id: "a"}, drafts: new Map([["a", "first"]])});
  elements.message = {value: "first"};
  elements["proposal-enabled"].checked = true;
  elements["proposal-fields"] = {hidden: false};
  elements["proposal-budget"].value = "100";
  const first = {chatId: "a", draft: "first", message: "first", proposal: readProposal(), requestId: "first-id"};
  context.sendApi.acknowledgeSend(first, {id: "a"});
  assert.equal(elements["proposal-enabled"].checked, true, "Successful send must retain proposal mode");
  assert.equal(elements["proposal-fields"].hidden, false, "Proposal fields must stay visible");
  assert.equal(elements["proposal-language"].value, "Python");
  elements["proposal-language"].value = "Java";
  const second = {chatId: "a", draft: "second", message: "second", proposal: readProposal(), requestId: "second-id"};
  assert.equal(second.proposal.language, "Java", "Next send reads edited proposal");
  const calls = [];
  context.request = async (url, method, data) => { calls.push({url, method, data}); return {chat: {id: "a", busy: false}}; };
  await context.sendApi.recoverSend(second);
  const replay = calls.find((call) => call.method === "POST");
  assert.equal(replay.data.request_id, "second-id");
  assert.equal(replay.data.proposal.language, "Java", "Recovery replays the same proposal");
  assert.equal(replay.data.proposal.budget, 100);
  assert.equal(elements["proposal-enabled"].checked, true);
  assert.equal(elements["proposal-fields"].hidden, false);
  console.log("Week UI checks passed: memory, proposal validation, stale response, repeat send and recovery.");
}
run().catch((error) => { console.error(error); process.exitCode = 1; });
