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
};
const messageHint = elements["message-hint"].textContent;
const nameHint = elements["name-hint"].textContent;
const desktop = matchMedia("(min-width: 60rem)");
let dialogOpener = null;

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
  const locked = Boolean(state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend);
  elements["new-chat"].disabled = locked;
  elements.send.disabled = locked || !state.chat || state.loadingChat;
  elements.send.setAttribute("aria-label", state.pendingChatId ? "Ответ готовится" : "Отправить сообщение");
  elements.message.disabled = !state.activeChatId;
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
    throw error;
  }
  return result;
}

function chatPath(id) {
  return "/api/chats/" + encodeURIComponent(id);
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

function renderChat(chat, animate = false) {
  const previousCount = state.chat?.id === chat.id ? state.chat.messages.length : 0;
  state.chat = chat;
  const fragment = document.createDocumentFragment();
  chat.messages.forEach((message, index) => {
    const assistant = message.role === "assistant";
    const item = document.createElement("li");
    item.className = "message " + (assistant ? "assistant" : "user");
    if (animate && assistant && index >= previousCount) item.classList.add("new-answer");
    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = assistant ? "GOOST" : "Ты";
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
  elements.stats.textContent = chat.message_count.toLocaleString("ru-RU") + " сообщений · "
    + chat.total_tokens.toLocaleString("ru-RU") + " токенов";
  elements.empty.hidden = Boolean(chat.messages.length);
  elements["empty-title"].textContent = "Начнём с твоего вопроса";
  elements["empty-description"].textContent = "Обсудим идею, разберём задачу или напишем текст. Каждый чат помнит свой разговор.";
  elements["empty-action"].textContent = "Написать сообщение";
  updateControls();
}

async function selectChat(id, focus = false) {
  saveDraft();
  const version = ++state.selectionVersion;
  state.activeChatId = id;
  state.chat = null;
  state.loadingChat = true;
  elements.message.value = state.drafts.get(id) || "";
  resetValidation();
  elements.messages.replaceChildren();
  elements.empty.hidden = false;
  elements["empty-title"].textContent = "Загружаю диалог…";
  elements["empty-description"].textContent = "Восстанавливаю сообщения.";
  elements["chat-title"].textContent = state.chats.find((chat) => chat.id === id)?.title || "Чат";
  elements.stats.textContent = "";
  renderList();
  try {
    const result = await request(chatPath(id));
    if (version !== state.selectionVersion) return;
    state.serverBusy = result.chat.busy;
    state.synchronized = true;
    state.loadingChat = false;
    renderChat(result.chat);
    elements.transcript.scrollTop = elements.transcript.scrollHeight;
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
  elements.message.value = "";
  elements.messages.replaceChildren();
  elements.empty.hidden = false;
  elements["chat-title"].textContent = "GOOST CHAT";
  elements["empty-title"].textContent = "Пока нет чатов";
  elements["empty-description"].textContent = "Создай чат, чтобы начать новый разговор.";
  elements["empty-action"].textContent = "Создать чат";
  elements.stats.textContent = "";
  renderList();
}

async function refreshList() {
  const result = await request("/api/chats");
  state.chats = result.chats;
  state.serverBusy = result.busy;
  state.synchronized = true;
  elements.model.textContent = result.model;
  renderList();
}

async function createChat() {
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend) return;
  state.pendingOperation = "create";
  setError();
  setStatus("Создаю чат…");
  updateControls();
  try {
    const result = await request("/api/chats", "POST", {});
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

function acknowledgeSend(transaction, chat) {
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
    ++state.selectionVersion;
    state.loadingChat = false;
    renderChat(chat, true);
    elements.transcript.scrollTop = elements.transcript.scrollHeight;
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
  });
  // A replay can return a cached snapshot; render the latest history instead.
  const latest = await request(chatPath(transaction.chatId));
  acknowledgeSend(transaction, latest.chat);
}

function handleSendError(error, transaction) {
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
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.loadingChat || !state.chat || state.uncertainSend) return;
  if (!validate(elements.message, elements["message-hint"], messageHint)) {
    elements.message.focus();
    return;
  }
  saveDraft();
  const transaction = {
    chatId: state.activeChatId,
    requestId: crypto.randomUUID(),
    message: elements.message.value.trim(),
    draft: elements.message.value,
  };
  state.pendingChatId = transaction.chatId;
  state.pendingOperation = "send";
  setError();
  setStatus("Модель готовит ответ. Это может занять около минуты.");
  updateControls();
  try {
    const result = await request(chatPath(transaction.chatId) + "/messages", "POST", {
      message: transaction.message,
      request_id: transaction.requestId,
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
    if (id) await selectChat(id);
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
}

function placeSidebar() {
  closeDrawer();
  (desktop.matches ? elements["sidebar-host"] : elements.drawer).append(elements.sidebar);
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

elements["new-chat"].addEventListener("click", createChat);
elements["message-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  submitMessage();
});
elements.message.addEventListener("input", () => {
  saveDraft();
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
  if (!state.activeChatId) createChat();
  else elements.message.focus();
});
elements["open-drawer"].addEventListener("click", () => elements.drawer.showModal());
elements["close-drawer"].addEventListener("click", closeDrawer);
elements["cancel-manage"].addEventListener("click", () => elements["manage-dialog"].close());
elements["cancel-delete"].addEventListener("click", () => elements["delete-dialog"].close());
[elements["manage-dialog"], elements["delete-dialog"]].forEach((dialog) => {
  dialog.addEventListener("close", restoreDialogFocus);
});
document.querySelectorAll("dialog").forEach((dialog) => {
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
});
desktop.addEventListener("change", placeSidebar);
placeSidebar();
synchronize(true);
