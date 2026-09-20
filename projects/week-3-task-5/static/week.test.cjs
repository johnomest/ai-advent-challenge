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
  elements["week-status"].textContent = "Chat B status";
  resolveRequest({chat: {id: "a"}});
  await pending;
  assert.equal(rendered.length, 0, "Late mutation must not replace another chat");
  assert.equal(state.pendingOperation, null);
  assert.equal(state.chat.id, "b");
  assert.equal(elements["week-status"].textContent, "Chat B status", "Late success must not leak status into another chat");
  context.request = async () => { state.activeChatId = "c"; throw Object.assign(new Error("Chat B failure"), {code: "invalid_transition"}); };
  elements["week-error"].textContent = "";
  await mutateWeek("/api/chats/b/task", "PATCH", {}, "Saved");
  assert.equal(elements["week-error"].textContent, "", "Late refusal must not leak into another chat");
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

  // Exercise the real task markup, listeners and state rendering with minimal DOM nodes.
  const weekSource = fs.readFileSync(path.join(__dirname, "week.js"), "utf8");
  const nodes = {};
  function node(id = "") {
    return {id, value: "", dataset: {}, textContent: "", disabled: false, checked: false,
      listeners: {}, children: [], setAttribute(key, value) { this[key] = value; },
      addEventListener(name, fn) { this.listeners[name] = fn; },
      replaceChildren(...children) { this.children = children; },
      querySelectorAll() {
        if (id === "week-panels") return Object.values(nodes).filter((item) => item !== this);
        const prefix = id.replace(/-form$/, "");
        return Object.values(nodes).filter((item) => item.id !== id && (item.id === prefix || item.id.startsWith(prefix + "-")));
      },
    };
  }
  for (const match of weekSource.matchAll(/id="([^"]+)"/g)) nodes[match[1]] = node(match[1]);
  for (const id of ["week-panels", "week-error", "week-status", "task-paused-hint", "send"]) nodes[id] = node(id);
  const taskState = {activeChatId: "a", synchronized: true, selectionVersion: 1, profiles: []};
  const taskCalls = [];
  const taskContext = vm.createContext({elements: nodes, state: taskState,
    document: {body: {dataset: {day: "15"}}, createElement() { return node(); }},
    chatPath(id) { return "/api/chats/" + id; }, upsertChat() {},
    request: async (url, method, data) => { taskCalls.push({url, method, data}); return {chat: taskState.chat}; },
    updateControls() { taskContext.api.updateWeekControls(Boolean(taskState.pendingOperation)); },
    renderChat(chat) { taskState.chat = chat; taskContext.api.renderWeek(chat); },
  });
  vm.runInContext(weekSource + "\nglobalThis.api = {initializeWeek, renderWeek, updateWeekControls, mutateTask};", taskContext);
  taskContext.api.initializeWeek();
  function chat(task = {}) {
    return {id: "a", task: {stage: "planning", paused: false, revision: 0, current_step: "", expected_action: "",
      plan: "", plan_approved: false, execution_result: "", validation: null, history: [], allowed_transitions: [],
      transition_reasons: {done: "Нельзя пропустить этап"}, ...task}};
  }
  taskContext.renderChat(chat());
  taskContext.updateControls();
  assert.equal(nodes["task-panel"].open, true);
  assert.equal(nodes["task-state"].textContent, "Планирование · ревизия 0");
  assert.equal(nodes["task-plan-approve"].disabled, true);
  assert.equal(nodes["task-execution-save"].disabled, true);
  assert.equal(nodes["task-target"].value, "execution");
  nodes["task-target"].value = "done";
  nodes["task-target"].listeners.change();
  assert.equal(nodes["task-transition-hint"].textContent, "Нельзя пропустить этап");
  assert.equal(nodes["task-transition"].disabled, false, "Forbidden target remains submit-capable so server can refuse it");
  const event = {preventDefault() { this.prevented = true; }};
  nodes["task-transition-form"].listeners.submit(event);
  await new Promise(setImmediate);
  assert.equal(event.prevented, true);
  assert.equal(taskCalls.at(-1).data.action, "transition");
  assert.equal(taskCalls.at(-1).data.target_stage, "done");
  assert.equal(taskCalls.at(-1).data.expected_revision, 0);

  taskContext.renderChat(chat({plan: "Saved plan", revision: 1}));
  nodes["task-plan"].value = "Unsaved local plan <script>alert(1)</script>";
  let attempts = 0;
  taskContext.request = async (url, method) => {
    attempts++;
    if (method === "PATCH") throw Object.assign(new Error("Ревизия устарела"), {code: "stale_revision"});
    return {chat: chat({plan: "Remote plan", revision: 2, current_step: "Remote step", history: [
      {revision: 2, action: "save_plan", from_stage: "planning", to_stage: "planning"},
    ]})};
  };
  await taskContext.api.mutateTask("save_plan", {plan: nodes["task-plan"].value});
  assert.equal(attempts, 2, "Conflict fetches current state without automatic write replay");
  assert.equal(taskState.chat.task.revision, 2);
  assert.equal(nodes["task-plan"].value, "Unsaved local plan <script>alert(1)</script>");
  assert.equal(nodes["task-step"].value, "Remote step", "Pristine field receives authoritative value");
  assert.match(nodes["week-status"].textContent, /Черновики сохранены/);
  assert.equal(nodes["task-history"].children[0].textContent, "#2 · План сохранён · Планирование");
  assert.equal(nodes["task-plan-approve"].disabled, true, "Unsaved draft cannot approve a different saved plan");
  for (const task of [{paused: true}, {stage: "done"}]) {
    taskContext.renderChat(chat(task)); taskContext.updateControls();
    assert.equal(nodes.send.disabled, true);
    assert.equal(nodes["task-transition"].disabled, true);
    assert.equal(nodes["task-plan-save"].disabled, true);
    assert.equal(nodes["task-pause"].disabled, task.stage === "done");
  }

  // Real submit handler must enforce pause/done even when invoked with Enter.
  vm.runInContext(appSource.slice(appSource.indexOf("async function submitMessage("), appSource.indexOf("async function synchronize(")) +
    "globalThis.submitMessage = submitMessage;", context);
  const sendErrors = [];
  context.setError = (message) => sendErrors.push(message);
  context.request = () => { throw new Error("Blocked task must not send a request"); };
  state.chat = {task: {paused: true, stage: "planning"}};
  await context.submitMessage();
  assert.match(sendErrors.at(-1), /паузе/);
  state.chat = {task: {paused: false, stage: "done"}};
  await context.submitMessage();
  assert.match(sendErrors.at(-1), /завершена/);
  console.log("Week UI checks passed: parsers, proposals/recovery, A→B response isolation, task rendering/submission, stale revision drafts, pause/done guards.");
}
run().catch((error) => { console.error(error); process.exitCode = 1; });
