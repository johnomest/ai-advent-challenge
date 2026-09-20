"use strict";

const elements = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((element) => [element.id, element]),
);
const state = {
  chats: [],
  activeChatId: null,
  chat: null,
  drafts: new Map(),
  pendingChatId: null,
  pendingOperation: null,
  selectionVersion: 0,
  loadingChat: false,
  synchronized: false,
  serverBusy: false,
  uncertainSend: null,
  managedChatId: null,
  preview: null,
  previewSequence: 0,
  previewTimer: null,
  branchTransaction: null,
  pendingMessage: null,
  profiles: [],
};
const strategyLabels = {sliding_window: "Скользящее окно", sticky_facts: "Ключевые факты", branching: "Ветки диалога"};
const messageHint = elements["message-hint"].textContent;
const nameHint = elements["name-hint"].textContent;
const desktop = matchMedia("(min-width: 60rem)");
const wideDesktop = matchMedia("(min-width: 80rem)");
let dialogOpener = null;
let focusedPanel = null;

function setStatus(message) {
  elements.status.textContent = message;
}

function setError(message = "") {
  elements.error.textContent = message;
  elements.error.hidden = !message;
}

function saveDraft() {
  if (state.activeChatId) state.drafts.set(state.activeChatId, elements.message.value);
}

function resetValidation() {
  elements.message.removeAttribute("aria-invalid");
  elements["message-hint"].classList.remove("invalid");
  elements["message-hint"].textContent = messageHint;
}

function validate(field, hint, normalHint) {
  const valid = Boolean(field.value.trim()) && field.value.length <= field.maxLength;
  field.setAttribute("aria-invalid", String(!valid));
  hint.classList.toggle("invalid", !valid);
  hint.textContent = valid ? normalHint : (
    field.value.trim() ? "Сократи текст до " + field.maxLength + " символов."
      : "Поле пустое. Добавь текст."
  );
  return valid;
}

function updateControls() {
  const scrollTop = elements.transcript.scrollTop;
  const locked = Boolean(state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend);
  elements["new-chat"].disabled = locked;
  elements.send.disabled = locked || !state.chat || state.loadingChat;
  elements.send.setAttribute("aria-label", state.pendingChatId ? "Ответ готовится" : "Отправить сообщение");
  elements.message.disabled = !state.activeChatId;
  const strategyLocked = locked || !state.chat || state.loadingChat || Boolean(state.chat?.messages.length);
  ["strategy", "window-turns", "save-strategy"].forEach((id) => { elements[id].disabled = strategyLocked; });
  elements["confirm-create"].disabled = locked;
  const branchLocked = locked || state.loadingChat || !state.chat || !elements["branch-checkpoint"].value;
  elements["branch-checkpoint"].disabled = branchLocked;
  elements["create-branches"].disabled = branchLocked;
  elements["memory-panel"].hidden = !state.chat || state.loadingChat;
  elements.sync.disabled = Boolean(state.pendingOperation);
  elements["message-form"].setAttribute("aria-busy", String(Boolean(state.pendingChatId)));
  elements["reply-pending"].hidden = state.pendingChatId !== state.activeChatId || !state.pendingChatId;
  elements["chat-list"].querySelectorAll("[data-action]").forEach((button) => {
    button.disabled = locked;
  });
  elements["empty-action"].disabled = state.loadingChat || Boolean(state.pendingOperation) || !state.synchronized;
  elements["save-name"].disabled = locked;
  elements["delete-chat"].disabled = locked;
  elements["confirm-delete"].disabled = locked;
  sizeTranscriptSpacer();
  elements.transcript.scrollTop = scrollTop;
  updateWeekControls(locked || !state.chat || state.loadingChat);
}

async function request(path, method = "GET", data) {
  let response;
  let result;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: data === undefined ? {} : {"Content-Type": "application/json"},
      body: data === undefined ? undefined : JSON.stringify(data),
      signal: AbortSignal.timeout(90000),
    });
    result = await response.json();
  } catch {
    const error = new Error("Связь с сервером прервалась. Проверь, что он запущен, и нажми «Обновить чаты и проверить связь».");
    error.code = "network";
    throw error;
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || "Не удалось выполнить запрос. Обнови чаты и проверь связь.");
    error.code = result.error?.code || "server_error";
    error.estimate = result.error?.estimate;
    throw error;
  }
  return result;
}

function chatPath(id) {
  return "/api/chats/" + encodeURIComponent(id);
}

function tokenCount(value, estimated = false) {
  return Number.isFinite(value) ? (estimated ? "≈ " : "") + value.toLocaleString("ru-RU") : "—";
}

function resetPreview() {
  clearTimeout(state.previewTimer);
  ++state.previewSequence;
  state.preview = null;
  elements["token-preview"].hidden = !state.chat;
  elements["token-details"].hidden = !state.chat;
  renderPreview();
}

function renderPreview(status) {
  const estimate = state.preview;
  const last = state.chat?.turn_metrics?.at(-1);
  elements["request-tokens"].textContent = tokenCount(estimate?.request_tokens, true);
  elements["history-tokens"].textContent = tokenCount(estimate?.history_tokens, true);
  elements["answer-tokens"].textContent = tokenCount(last?.answer_tokens, true)
    + " · API " + tokenCount(last?.provider_usage?.completion_tokens);
  elements["context-budget"].textContent = estimate
    ? "С резервом ответа: " + tokenCount(estimate.required_tokens, true) + " / " + tokenCount(estimate.context_limit)
    : "Контекст: —";
  elements["context-meter"].max = estimate?.context_limit || 1;
  elements["context-meter"].value = Math.min(estimate?.required_tokens || 0, elements["context-meter"].max);
  elements["context-meter"].setAttribute("aria-valuetext", elements["context-budget"].textContent);
  elements["token-preview"].classList.toggle("overflow", Boolean(estimate?.overflow));
  elements["preview-status"].textContent = status || (estimate?.overflow
    ? "Лимит превышен. Отправка покажет ошибку; история и черновик сохранятся."
    : estimate ? "Осталось ≈ " + tokenCount(Math.max(0, estimate.remaining_tokens)) + " токенов с учётом резерва ответа."
      : "Нет оценки контекста.");
  const fields = [
    ["Система", "system_tokens"], ["История", "history_tokens"],
    ["Новый запрос", "request_tokens"], ["Служебная разметка", "message_overhead_tokens"],
    ["Вход целиком", "prompt_tokens"], ["Резерв ответа", "reserved_output_tokens"],
    ["Всего с резервом", "required_tokens"], ["Лимит контекста", "context_limit"],
  ];
  elements["context-fields"].replaceChildren(...fields.flatMap(([label, key]) => {
    const term = document.createElement("dt");
    const value = document.createElement("dd");
    term.textContent = label;
    value.textContent = tokenCount(estimate?.[key], !["reserved_output_tokens", "context_limit"].includes(key));
    return [term, value];
  }));
  elements["estimator-note"].textContent = estimate?.estimator
    ? "Метод оценки: " + estimate.estimator + ". Фактический подсчёт API может отличаться." : "";
  renderMemory();
}

function renderMemory() {
  const chat = state.chat;
  if (!chat) return;
  const estimate = state.preview;
  const strategy = chat.strategy || "sliding_window";
  const total = estimate?.total_turns ?? Math.floor(chat.messages.length / 2);
  const selected = estimate?.selected_turns;
  const scope = Number.isFinite(selected) ? selected + " из " + total + " ходов"
    : strategy === "branching" ? "вся история этой ветки" : "последние " + chat.window_turns + " ходов";
  elements["memory-context"].textContent = "Системная инструкция, " + scope + ", текущий запрос"
    + (strategy === "sticky_facts" ? " и сохранённые факты." : ".")
    + " Также: три слоя памяти"
    + (weekDay >= 12 ? ", выбранный профиль" : "")
    + (weekDay >= 13 ? ", состояние задачи" : "")
    + (weekDay >= 14 ? ", инварианты" : "")
    + ". Полная переписка остаётся в чате.";
  const facts = Array.isArray(chat.facts) ? chat.facts
    : Object.entries(chat.facts || {}).map(([key, value]) => key + ": " + value);
  elements["memory-facts"].replaceChildren(...facts.map((fact) => {
    const item = document.createElement("li");
    item.textContent = typeof fact === "string" ? fact : JSON.stringify(fact);
    return item;
  }));
  if (strategy === "sticky_facts" && !facts.length) {
    const item = document.createElement("li");
    item.textContent = "Сохранённых фактов пока нет.";
    elements["memory-facts"].append(item);
  }
}

function schedulePreview() {
  resetPreview();
  if (!state.chat || state.loadingChat) return;
  const chatId = state.activeChatId;
  const draft = elements.message.value;
  const sequence = state.previewSequence;
  if (!draft.trim()) state.preview = state.chat.context || null;
  renderPreview("Считаю контекст…");
  const isCurrent = () => sequence === state.previewSequence
    && chatId === state.activeChatId && draft === elements.message.value;
  state.previewTimer = setTimeout(async () => {
    try {
      const result = await request(chatPath(chatId) + "/token-preview", "POST", {message: draft.trim()});
      if (!isCurrent()) return;
      state.preview = result.estimate;
      renderPreview();
    } catch {
      if (!isCurrent()) return;
      state.preview = null;
      renderPreview("Оценка недоступна. Измени текст или обнови чаты, чтобы повторить.");
    }
  }, 300);
}

function renderTurnMetrics(chat) {
  const metrics = chat.turn_metrics || [];
  elements["metrics-empty"].hidden = Boolean(metrics.length);
  elements["turn-metrics"].replaceChildren(...metrics.map((turn) => {
    const row = document.createElement("tr");
    const cost = turn.cost;
    const minCost = cost?.min_usd == null ? NaN : Number(cost.min_usd);
    const maxCost = cost?.max_usd == null ? NaN : Number(cost.max_usd);
    const money = (value) => value.toLocaleString("ru-RU", {minimumFractionDigits: 6, maximumFractionDigits: 6});
    const costLabel = Number.isFinite(minCost) && Number.isFinite(maxCost)
      ? "≈ $" + money(minCost) + (minCost === maxCost ? "" : "–$" + money(maxCost)) : "—";
    [tokenCount(turn.turn_index), tokenCount(turn.request_tokens), tokenCount(turn.history_tokens),
      tokenCount(turn.provider_usage?.prompt_tokens), tokenCount(turn.answer_tokens),
      tokenCount(turn.provider_usage?.completion_tokens), costLabel].forEach((text, index) => {
      const cell = document.createElement(index === 0 ? "th" : "td");
      if (index === 0) cell.scope = "row";
      cell.textContent = text;
      if (index === 6 && cost) {
        const source = document.createElement("small");
        source.textContent = [cost.pricing_date, cost.source].filter(Boolean).join(" · ");
        cell.append(source);
      }
      row.append(cell);
    });
    return row;
  }));
}

function upsertChat(chat) {
  const previous = state.chats.find((item) => item.id === chat.id);
  state.chats = state.chats.filter((item) => item.id !== chat.id);
  state.chats.unshift({...previous, ...chat});
  state.chats.sort((a, b) => b.updated_at - a.updated_at);
  renderList();
}

function renderList() {
  const fragment = document.createDocumentFragment();
  state.chats.forEach((chat) => {
    const item = document.createElement("li");
    item.className = "chat-row";
    item.classList.toggle("selected", chat.id === state.activeChatId);
    const select = document.createElement("button");
    select.type = "button";
    select.className = "chat-select";
    select.title = chat.title;
    if (chat.id === state.activeChatId) select.setAttribute("aria-current", "page");
    const title = document.createElement("span");
    title.textContent = chat.title;
    select.append(title);
    if (chat.branch_label) {
      const lineage = document.createElement("small");
      lineage.textContent = "Ветка " + chat.branch_label + " · ход " + chat.checkpoint_turn;
      select.append(lineage);
    }
    select.addEventListener("click", () => {
      closeDrawer();
      selectChat(chat.id, true);
    });
    const actions = document.createElement("button");
    actions.type = "button";
    actions.className = "icon-button";
    actions.dataset.action = chat.id;
    actions.textContent = "⋯";
    actions.setAttribute("aria-label", "Переименовать или удалить чат «" + chat.title + "»");
    actions.setAttribute("aria-haspopup", "dialog");
    actions.addEventListener("click", () => openManage(chat, actions));
    item.append(select, actions);
    fragment.append(item);
  });
  elements["chat-list"].replaceChildren(fragment);
  elements["chat-count"].textContent = state.chats.length.toLocaleString("ru-RU");
  elements["list-empty"].hidden = Boolean(state.chats.length);
  elements["list-empty"].textContent = state.synchronized ? "Пока нет чатов." : "Загружаю чаты…";
  updateControls();
}

function sizeTranscriptSpacer() {
  const last = elements.messages.lastElementChild;
  if (!last) {
    elements["transcript-spacer"].style.height = "0px";
    return;
  }
  const tail = elements["transcript-spacer"].getBoundingClientRect().top - last.getBoundingClientRect().top;
  const inset = parseFloat(getComputedStyle(elements.transcript).paddingTop) || 0;
  elements["transcript-spacer"].style.height = Math.max(0, elements.transcript.clientHeight - tail - inset) + "px";
}

function anchorMessage(item) {
  if (!item) {
    elements.transcript.scrollTop = 0;
    return;
  }
  sizeTranscriptSpacer();
  const inset = parseFloat(getComputedStyle(elements.transcript).paddingTop) || 0;
  elements.transcript.scrollTop += item.getBoundingClientRect().top - elements.transcript.getBoundingClientRect().top - inset;
}

function renderChat(chat, {animate = false, anchor = "preserve"} = {}) {
  const scrollTop = elements.transcript.scrollTop;
  const sameChat = state.chat?.id === chat.id;
  const previousCount = sameChat ? state.chat.messages.length : 0;
  state.chat = chat;
  const fragment = document.createDocumentFragment();
  const pending = state.pendingMessage;
  const showPending = pending?.chatId === chat.id && chat.messages.length <= pending.baseCount;
  const messages = showPending ? [...chat.messages, {role: "user", content: pending.message, temporary: true}] : chat.messages;
  messages.forEach((message, index) => {
    const assistant = message.role === "assistant";
    const item = document.createElement("li");
    item.className = "message " + (assistant ? "assistant" : "user");
    item.dataset.messageIndex = String(index);
    if (message.temporary) item.dataset.pending = "true";
    if (animate && assistant && index >= previousCount) item.classList.add("new-answer");
    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = assistant ? "GOOST" : message.temporary ? "Ты · отправляется" : "Ты";
    const content = document.createElement("p");
    content.className = "message-content";
    content.textContent = message.content;
    item.append(author, content);
    if (assistant) {
      const copy = document.createElement("button");
      copy.className = "button copy";
      copy.type = "button";
      copy.textContent = "Скопировать";
      copy.setAttribute("aria-label", "Скопировать ответ " + (Math.floor(index / 2) + 1));
      copy.addEventListener("click", async () => {
        copy.disabled = true;
        try {
          await navigator.clipboard.writeText(message.content);
          copy.textContent = "Скопировано";
          copy.dataset.state = "copied";
          setStatus("Ответ скопирован.");
        } catch {
          copy.textContent = "Не скопировано";
          copy.dataset.state = "error";
          setStatus("Выдели текст ответа и скопируй вручную.");
        } finally {
          copy.disabled = false;
          setTimeout(() => {
            copy.textContent = "Скопировать";
            delete copy.dataset.state;
          }, 2500);
        }
      });
      item.append(copy);
    }
    fragment.append(item);
  });
  elements.messages.replaceChildren(fragment);
  elements["chat-title"].textContent = chat.title;
  elements.model.textContent = chat.model;
  elements.stats.textContent = chat.message_count.toLocaleString("ru-RU") + " сообщений";
  elements.empty.hidden = Boolean(messages.length);
  elements["empty-title"].textContent = "Начнём с твоего вопроса";
  elements["empty-description"].textContent = "Обсудим идею, разберём задачу или напишем текст. Каждый чат помнит свой разговор.";
  elements["empty-action"].textContent = "Написать сообщение";
  elements.strategy.value = chat.strategy || "sliding_window";
  elements["window-turns"].value = chat.window_turns || 3;
  elements["strategy-hint"].textContent = chat.messages.length
    ? strategyLabels[chat.strategy] + ". Для другой стратегии создай новый чат. Ход — вопрос и ответ."
    : "Стратегию можно менять до первого сообщения. Ход — вопрос и ответ.";
  elements["branch-lineage"].hidden = !chat.parent_id;
  elements["branch-lineage"].textContent = chat.parent_id
    ? "Ветка " + chat.branch_label + " · из «" + (state.chats.find((item) => item.id === chat.parent_id)?.title || "исходного чата") + "» · после хода " + chat.checkpoint_turn : "";
  const previousCheckpoint = sameChat ? elements["branch-checkpoint"].value : "";
  elements["branch-form"].hidden = chat.strategy !== "branching";
  elements["branch-checkpoint"].replaceChildren(...chat.messages.flatMap((message, index) => {
    if (message.role !== "assistant") return [];
    const option = document.createElement("option");
    option.value = String(Math.floor(index / 2) + 1);
    option.textContent = "После хода " + option.value + " · " + message.content.slice(0, 60);
    return [option];
  }));
  const checkpoints = elements["branch-checkpoint"].options;
  elements["branch-checkpoint"].value = [...checkpoints].some((option) => option.value === previousCheckpoint)
    ? previousCheckpoint : checkpoints[checkpoints.length - 1]?.value || "";
  elements["branch-hint"].textContent = checkpoints.length
    ? "Выбери завершённый ход для двух независимых продолжений." : "Точки ветвления появятся после первого ответа.";
  renderTurnMetrics(chat);
  renderWeek(chat);
  schedulePreview();
  updateControls();
  sizeTranscriptSpacer();
  if (anchor === "pending") anchorMessage(elements.messages.querySelector("[data-pending]"));
  else if (anchor === "latest") anchorMessage([...elements.messages.querySelectorAll(".assistant")].at(-1) || elements.messages.lastElementChild);
  else elements.transcript.scrollTop = scrollTop;
}

async function selectChat(id, focus = false, preserveScroll = false) {
  saveDraft();
  preserveScroll = preserveScroll && state.chat?.id === id;
  const version = ++state.selectionVersion;
  state.activeChatId = id;
  if (!preserveScroll) state.chat = null;
  state.loadingChat = true;
  resetPreview();
  elements.message.value = state.drafts.get(id) || "";
  resetValidation();
  if (!preserveScroll) {
    elements.messages.replaceChildren();
    sizeTranscriptSpacer();
    elements.empty.hidden = false;
  }
  elements["empty-title"].textContent = "Загружаю диалог…";
  elements["empty-description"].textContent = "Восстанавливаю сообщения.";
  elements["chat-title"].textContent = state.chats.find((chat) => chat.id === id)?.title || "Чат";
  elements.stats.textContent = "";
  renderList();
  if (!preserveScroll) elements.transcript.scrollTop = 0;
  try {
    const result = await request(chatPath(id));
    if (version !== state.selectionVersion) return;
    state.serverBusy = result.chat.busy;
    state.synchronized = true;
    state.loadingChat = false;
    renderChat(result.chat, {anchor: preserveScroll ? "preserve" : "latest"});
    if (focus) elements.message.focus({preventScroll: true});
    if (!state.pendingOperation && !state.uncertainSend) {
      setStatus(state.serverBusy ? "Ответ ещё готовится. Обнови чаты через несколько секунд." : "Можно продолжать.");
    }
  } catch (error) {
    if (version !== state.selectionVersion) return;
    state.synchronized = false;
    elements["empty-title"].textContent = "Не удалось открыть чат";
    elements["empty-description"].textContent = "Обнови чаты и проверь связь. Черновик сохранён.";
    setError(error.message);
    setStatus("Диалог не загружен.");
  } finally {
    if (version === state.selectionVersion) {
      state.loadingChat = false;
      updateControls();
    }
  }
}

function showNoChats() {
  saveDraft();
  ++state.selectionVersion;
  state.activeChatId = null;
  state.chat = null;
  state.loadingChat = false;
  resetPreview();
  elements.message.value = "";
  elements.messages.replaceChildren();
  sizeTranscriptSpacer();
  elements.empty.hidden = false;
  elements["chat-title"].textContent = "GOOST CHAT";
  elements["empty-title"].textContent = "Пока нет чатов";
  elements["empty-description"].textContent = "Создай чат, чтобы начать новый разговор.";
  elements["empty-action"].textContent = "Создать чат";
  elements.stats.textContent = "";
  renderList();
  elements.transcript.scrollTop = 0;
}

async function refreshList() {
  if (weekDay >= 12) state.profiles = (await request("/api/profiles")).profiles;
  const result = await request("/api/chats");
  state.chats = result.chats;
  state.serverBusy = result.busy;
  state.synchronized = true;
  elements.model.textContent = result.model;
  renderList();
}

async function createChat(settings = {strategy: "sliding_window", window_turns: 3}) {
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend) return;
  state.pendingOperation = "create";
  setError();
  setStatus("Создаю чат…");
  updateControls();
  try {
    const result = await request("/api/chats", "POST", settings);
    elements["create-dialog"].close();
    upsertChat(result.chat);
    await selectChat(result.chat.id, true);
    closeDrawer();
    setStatus("Новый чат готов.");
  } catch (error) {
    setError(error.message);
    if (error.code === "network") state.synchronized = false;
    if (error.code === "busy") state.serverBusy = true;
    setStatus("Проверь список перед повторным созданием чата.");
  } finally {
    state.pendingOperation = null;
    updateControls();
  }
}

async function saveStrategy(event) {
  event.preventDefault();
  if (elements["save-strategy"].disabled) return;
  const chatId = state.activeChatId;
  const settings = {strategy: elements.strategy.value, window_turns: Number(elements["window-turns"].value)};
  state.pendingOperation = "strategy";
  resetPreview();
  updateControls();
  setError();
  try {
    const result = await request(chatPath(chatId), "PATCH", settings);
    upsertChat(result.chat);
    if (state.activeChatId === chatId) renderChat(result.chat);
    setStatus("Стратегия сохранена.");
  } catch (error) {
    setError(error.message);
    if (error.code === "network") state.synchronized = false;
    if (state.activeChatId === chatId && state.chat) renderChat(state.chat);
  } finally {
    state.pendingOperation = null;
    updateControls();
  }
}

async function createBranches(chatId, checkpoint) {
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend) return;
  const previous = state.branchTransaction;
  const transaction = previous?.chatId === chatId && previous.checkpoint === checkpoint
    ? previous : {chatId, checkpoint, requestId: crypto.randomUUID()};
  state.branchTransaction = transaction;
  state.pendingOperation = "branch";
  setError();
  setStatus("Создаю две ветки…");
  updateControls();
  try {
    const result = await request(chatPath(chatId) + "/branches", "POST", {
      checkpoint_turn: checkpoint, request_id: transaction.requestId,
    });
    result.branches.forEach(upsertChat);
    state.branchTransaction = null;
    if (state.activeChatId === chatId) {
      closeInspector();
      await selectChat(result.branches[0].id, true);
    }
    setStatus("Ветки A и B готовы. Переключай их в списке чатов.");
  } catch (error) {
    setError(error.message);
    if (error.code === "network") state.synchronized = false;
    if (!["network", "server_error"].includes(error.code)) state.branchTransaction = null;
    setStatus("Обнови чаты. Повтор на том же ходе проверит создание веток.");
  } finally {
    state.pendingOperation = null;
    updateControls();
  }
}

function acknowledgeSend(transaction, chat) {
  state.pendingMessage = null;
  const draft = state.drafts.get(transaction.chatId);
  if (draft === transaction.draft) {
    state.drafts.set(transaction.chatId, "");
    if (state.activeChatId === transaction.chatId) elements.message.value = "";
  }
  state.uncertainSend = null;
  state.synchronized = true;
  state.serverBusy = false;
  upsertChat(chat);
  if (state.activeChatId === transaction.chatId) {
    const anchor = state.selectionVersion === transaction.selectionVersion ? "latest" : "preserve";
    ++state.selectionVersion;
    state.loadingChat = false;
    renderChat(chat, {animate: true, anchor});
    resetValidation();
  }
  setError();
  setStatus(state.activeChatId === transaction.chatId ? "Ответ готов." : "Ответ готов в другом чате.");
}

async function recoverSend(transaction) {
  // Read before replaying. Reusing the request ID cannot create a second saved answer.
  const current = await request(chatPath(transaction.chatId));
  if (state.activeChatId === transaction.chatId) {
    ++state.selectionVersion;
    state.loadingChat = false;
    renderChat(current.chat);
  }
  state.serverBusy = current.chat.busy;
  state.synchronized = true;
  if (current.chat.busy) {
    state.uncertainSend = transaction;
    setStatus("Ответ ещё готовится. Обнови чаты через несколько секунд.");
    return;
  }
  await request(chatPath(transaction.chatId) + "/messages", "POST", {
    message: transaction.message,
    request_id: transaction.requestId,
    ...(transaction.proposal ? {proposal: transaction.proposal} : {}),
  });
  // A replay can return a cached snapshot; render the latest history instead.
  const latest = await request(chatPath(transaction.chatId));
  acknowledgeSend(transaction, latest.chat);
}

function handleSendError(error, transaction) {
  state.pendingMessage = null;
  if (state.activeChatId === transaction.chatId && state.chat) renderChat(state.chat);
  if (error.code === "context_limit" && error.estimate
      && state.activeChatId === transaction.chatId && elements.message.value === transaction.draft) {
    clearTimeout(state.previewTimer);
    ++state.previewSequence;
    state.preview = error.estimate;
    renderPreview();
  }
  const unresolved = ["network", "server_error"].includes(error.code);
  state.uncertainSend = unresolved ? transaction : null;
  if (error.code === "network") state.synchronized = false;
  if (error.code === "busy") state.serverBusy = true;
  if (error.code === "request_pending") {
    setError("Статус прошлого запроса неизвестен. Текст сохранён — отправь его заново, если готов повторить запрос.");
    setStatus("Проверь историю перед новой отправкой.");
  } else {
    setError(error.message);
    setStatus(unresolved ? "Черновик сохранён. Обнови чаты перед повтором." : "Черновик сохранён. Можно исправить текст или повторить отправку.");
  }
}

async function submitMessage() {
  if (state.chat?.task?.paused) { setError("Задача на паузе. Нажми «Продолжить задачу» в панели состояния."); return; }
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.loadingChat || !state.chat || state.uncertainSend) return;
  if (!validate(elements.message, elements["message-hint"], messageHint)) {
    elements.message.focus();
    return;
  }
  saveDraft();
  let proposal;
  try { proposal = readProposal(); } catch (error) { setWeekError(error.message); setError(error.message); return; }
  const transaction = {
    chatId: state.activeChatId,
    requestId: crypto.randomUUID(),
    message: elements.message.value.trim(),
    draft: elements.message.value,
    baseCount: state.chat.messages.length,
    selectionVersion: state.selectionVersion,
    proposal,
  };
  state.pendingMessage = transaction;
  state.pendingChatId = transaction.chatId;
  state.pendingOperation = "send";
  setError();
  setStatus("Модель готовит ответ. Это может занять около минуты.");
  updateControls();
  renderChat(state.chat, {anchor: "pending"});
  try {
    const result = await request(chatPath(transaction.chatId) + "/messages", "POST", {
      message: transaction.message,
      request_id: transaction.requestId,
      ...(transaction.proposal ? {proposal: transaction.proposal} : {}),
    });
    acknowledgeSend(transaction, result.chat);
  } catch (error) {
    if (error.code === "network") {
      try {
        await recoverSend(transaction);
      } catch (recoveryError) {
        handleSendError(recoveryError, transaction);
      }
    } else {
      handleSendError(error, transaction);
    }
  } finally {
    state.pendingOperation = null;
    state.pendingChatId = null;
    updateControls();
  }
}

async function synchronize(bootstrap = false) {
  if (state.pendingOperation) return;
  state.pendingOperation = "sync";
  setError();
  setStatus("Проверяю чаты…");
  updateControls();
  try {
    await refreshList();
    if (state.uncertainSend) {
      const transaction = state.uncertainSend;
      try {
        await recoverSend(transaction);
      } catch (error) {
        handleSendError(error, transaction);
      }
    }
    const id = state.chats.some((chat) => chat.id === state.activeChatId)
      ? state.activeChatId : state.chats[0]?.id;
    if (id) await selectChat(id, false, true);
    else showNoChats();
    if (!state.uncertainSend && elements.error.hidden) {
      setStatus(state.serverBusy ? "Ответ ещё готовится. Обнови чаты через несколько секунд." : "Чаты обновлены.");
    }
  } catch (error) {
    state.synchronized = false;
    setError(error.message);
    setStatus("Связь не подтверждена. Проверь, что сервер запущен.");
  } finally {
    state.pendingOperation = null;
    updateControls();
  }
  if (bootstrap && state.synchronized && !state.chats.length && !state.serverBusy) await createChat();
}

function closeDrawer() {
  if (elements.drawer.open) elements.drawer.close();
  elements["open-drawer"].setAttribute("aria-expanded", "false");
}

function closeInspector() {
  if (elements["inspector-drawer"].open) elements["inspector-drawer"].close();
  elements["open-inspector"].setAttribute("aria-expanded", "false");
}

function placeSidebar() {
  const focused = elements.drawer.open || focusedPanel === "sidebar" || elements.sidebar.contains(document.activeElement);
  closeDrawer();
  (desktop.matches ? elements["sidebar-host"] : elements.drawer).append(elements.sidebar);
  if (focused) (desktop.matches ? elements["new-chat"] : elements["open-drawer"]).focus({preventScroll: true});
}

function placeInspector() {
  // The breakpoint can hide the focused close button before the media event runs.
  const focused = elements["inspector-drawer"].open || focusedPanel === "inspector" || elements.inspector.contains(document.activeElement);
  closeInspector();
  (wideDesktop.matches ? elements["inspector-host"] : elements["inspector-drawer"]).append(elements.inspector);
  if (focused) {
    const target = wideDesktop.matches ? (elements.sync.disabled ? elements["inspector-title"] : elements.sync) : elements["open-inspector"];
    if (target === elements["inspector-title"]) target.tabIndex = -1;
    target.focus({preventScroll: true});
  }
}

function restoreDialogFocus() {
  if (desktop.matches && dialogOpener?.isConnected) dialogOpener.focus({preventScroll: true});
  else if (!desktop.matches) elements["open-drawer"].focus({preventScroll: true});
  else elements.message.focus({preventScroll: true});
}

function openManage(chat, opener) {
  if (opener.disabled) return;
  closeDrawer();
  dialogOpener = opener;
  state.managedChatId = chat.id;
  elements["chat-name"].value = chat.title;
  elements["chat-name"].removeAttribute("aria-invalid");
  elements["name-hint"].classList.remove("invalid");
  elements["name-hint"].textContent = nameHint;
  elements["manage-dialog"].showModal();
  elements["chat-name"].focus();
  elements["chat-name"].select();
}

elements["rename-form"].addEventListener("submit", async (event) => {
  event.preventDefault();
  if (state.pendingOperation || !state.synchronized || state.serverBusy) return;
  if (!validate(elements["chat-name"], elements["name-hint"], nameHint)) {
    elements["chat-name"].focus();
    return;
  }
  const id = state.managedChatId;
  const title = elements["chat-name"].value.trim();
  elements["manage-dialog"].close();
  state.pendingOperation = "rename";
  updateControls();
  setError();
  try {
    const result = await request(chatPath(id), "PATCH", {title});
    upsertChat(result.chat);
    if (state.activeChatId === id) {
      elements["chat-title"].textContent = result.chat.title;
      if (state.chat) state.chat.title = result.chat.title;
    }
    setStatus("Название сохранено.");
  } catch (error) {
    setError(error.message);
    if (error.code === "network") state.synchronized = false;
    if (error.code === "busy") state.serverBusy = true;
    setStatus("Обнови чаты, чтобы проверить название.");
  } finally {
    state.pendingOperation = null;
    updateControls();
    restoreDialogFocus();
  }
});

elements["delete-chat"].addEventListener("click", () => {
  const chat = state.chats.find((item) => item.id === state.managedChatId);
  if (!chat) return;
  elements["manage-dialog"].close();
  elements["delete-description"].textContent = "Чат «" + chat.title + "» и вся его переписка будут удалены без возможности восстановления.";
  elements["delete-dialog"].showModal();
  elements["cancel-delete"].focus();
});

elements["confirm-delete"].addEventListener("click", async () => {
  if (state.pendingOperation || !state.synchronized || state.serverBusy) return;
  const id = state.managedChatId;
  elements["delete-dialog"].close();
  state.pendingOperation = "delete";
  updateControls();
  setError();
  try {
    await request(chatPath(id), "DELETE");
    state.drafts.delete(id);
    state.chats = state.chats.filter((chat) => chat.id !== id);
    if (state.activeChatId === id) {
      state.activeChatId = null;
      if (state.chats.length) await selectChat(state.chats[0].id);
      else showNoChats();
    }
    renderList();
    setStatus("Чат удалён.");
  } catch (error) {
    setError(error.message);
    if (error.code === "network") state.synchronized = false;
    if (error.code === "busy") state.serverBusy = true;
    setStatus("Обнови чаты, чтобы проверить результат удаления.");
  } finally {
    state.pendingOperation = null;
    updateControls();
    restoreDialogFocus();
  }
});

function openCreate() {
  closeDrawer();
  closeInspector();
  dialogOpener = elements["new-chat"];
  elements["create-dialog"].showModal();
  elements["new-strategy"].focus();
}
elements["new-chat"].addEventListener("click", openCreate);
elements["create-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  createChat({strategy: elements["new-strategy"].value, window_turns: Number(elements["new-window-turns"].value)});
});
elements["cancel-create"].addEventListener("click", () => elements["create-dialog"].close());
elements["strategy-form"].addEventListener("submit", saveStrategy);
elements["branch-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  if (!elements["create-branches"].disabled) createBranches(state.activeChatId, Number(elements["branch-checkpoint"].value));
});
elements["message-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  submitMessage();
});
elements.message.addEventListener("input", () => {
  saveDraft();
  schedulePreview();
  if (elements.message.hasAttribute("aria-invalid")) validate(elements.message, elements["message-hint"], messageHint);
});
elements.message.addEventListener("blur", () => {
  if (!elements.message.disabled && elements.message.value) validate(elements.message, elements["message-hint"], messageHint);
});
elements.message.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.isComposing && (!event.shiftKey || event.ctrlKey || event.metaKey)) {
    event.preventDefault();
    elements["message-form"].requestSubmit();
  }
});
elements["chat-name"].addEventListener("blur", () => validate(elements["chat-name"], elements["name-hint"], nameHint));
elements["chat-name"].addEventListener("input", () => {
  if (elements["chat-name"].hasAttribute("aria-invalid")) validate(elements["chat-name"], elements["name-hint"], nameHint);
});
elements.sync.addEventListener("click", () => synchronize());
elements["empty-action"].addEventListener("click", () => {
  if (!state.activeChatId) openCreate();
  else elements.message.focus();
});
elements["open-drawer"].addEventListener("click", () => {
  closeInspector();
  elements.drawer.showModal();
  elements["open-drawer"].setAttribute("aria-expanded", "true");
  elements["close-drawer"].focus();
});
elements["close-drawer"].addEventListener("click", closeDrawer);
elements["open-inspector"].addEventListener("click", () => {
  closeDrawer();
  elements["inspector-drawer"].showModal();
  elements["open-inspector"].setAttribute("aria-expanded", "true");
  elements["close-inspector"].focus();
});
elements["close-inspector"].addEventListener("click", closeInspector);
elements.drawer.addEventListener("close", () => {
  elements["open-drawer"].setAttribute("aria-expanded", "false");
});
elements["inspector-drawer"].addEventListener("close", () => {
  elements["open-inspector"].setAttribute("aria-expanded", "false");
});
elements["cancel-manage"].addEventListener("click", () => elements["manage-dialog"].close());
elements["cancel-delete"].addEventListener("click", () => elements["delete-dialog"].close());
[elements["manage-dialog"], elements["delete-dialog"], elements["create-dialog"]].forEach((dialog) => {
  dialog.addEventListener("close", restoreDialogFocus);
});
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
});
// Keep focus ownership when a breakpoint hides its control before the media event.
document.addEventListener("focusin", (event) => {
  if (event.target === document.body) return;
  focusedPanel = elements.inspector.contains(event.target) ? "inspector"
    : elements.sidebar.contains(event.target) ? "sidebar" : null;
});
desktop.addEventListener("change", placeSidebar);
wideDesktop.addEventListener("change", placeInspector);
new ResizeObserver(sizeTranscriptSpacer).observe(elements.transcript);
new ResizeObserver(sizeTranscriptSpacer).observe(elements.messages);
initializeWeek();
placeSidebar();
placeInspector();
synchronize(true);
