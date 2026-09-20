"use strict";

const weekDay = Number(document.body.dataset.day);
const taskStages = {planning: "Планирование", execution: "Выполнение", validation: "Проверка", done: "Завершено"};
let weekChatId = null;

function setWeekError(message = "") {
  elements["week-error"].textContent = message;
  elements["week-error"].hidden = !message;
}

function initializeWeek() {
  // Static markup only. Every server value is assigned through value/textContent.
  elements["week-panels"].innerHTML = `
    <details id="layers-panel" class="week-panel"><summary>Слои памяти</summary>
      <p class="muted">Все три слоя входят в контекст. Правки сохраняются только кнопкой.</p>
      <form id="short-memory-form" class="memory-controls">
        <label for="short-memory">Краткосрочная · текущий разговор</label>
        <textarea id="short-memory" rows="3" maxlength="3700" placeholder="тема = запуск проекта" aria-describedby="memory-entry-hint"></textarea>
        <button class="button secondary" type="submit">Сохранить краткосрочную</button>
      </form>
      <form id="working-memory-form" class="memory-controls">
        <label for="working-memory">Рабочая · текущая задача</label>
        <textarea id="working-memory" rows="3" maxlength="3700" placeholder="цель = подготовить план" aria-describedby="memory-entry-hint"></textarea>
        <button class="button secondary" type="submit">Сохранить рабочую</button>
      </form>
      <form id="long-memory-form" class="memory-controls">
        <label for="long-memory">Долговременная · все чаты</label>
        <textarea id="long-memory" rows="3" maxlength="3700" placeholder="язык = русский" aria-describedby="memory-entry-hint"></textarea>
        <button class="button secondary" type="submit">Сохранить долговременную</button>
      </form>
      <p id="memory-entry-hint" class="muted">Одна строка: ключ = значение. До 12 записей; ключ — 60, значение — 240 символов. Пустое поле очищает слой.</p>
    </details>
    <details id="profiles-panel" class="week-panel"><summary>Профиль пользователя</summary>
      <form id="profile-select-form" class="memory-controls">
        <label for="profile-select">Профиль этого чата</label><select id="profile-select"></select>
        <button class="button secondary" type="submit">Применить профиль</button>
      </form>
      <p class="muted">Стиль, формат и ограничения профиля входят в каждый следующий запрос.</p>
      <details class="memory-details"><summary>Создать или изменить профиль</summary>
        <form id="profile-editor" class="memory-controls">
          <label>Название<input id="profile-name" maxlength="80" required placeholder="Например, разработчик"></label>
          <label>Стиль ответа<textarea id="profile-style" rows="2" maxlength="500" placeholder="Кратко, с техническими деталями"></textarea></label>
          <label>Формат<textarea id="profile-format" rows="2" maxlength="500" placeholder="Список шагов и пример кода"></textarea></label>
          <label>Ограничения<textarea id="profile-constraints" rows="2" maxlength="500" placeholder="Без внешних зависимостей"></textarea></label>
          <button id="profile-save" class="button secondary" type="submit">Сохранить выбранный</button>
          <button id="profile-create" class="button secondary" type="button">Создать новый профиль</button>
          <button id="profile-delete" class="button secondary" type="button">Удалить выбранный</button>
        </form>
        <p class="muted">Изменение профиля действует во всех использующих его чатах.</p>
      </details>
    </details>
    <details id="task-panel" class="week-panel"><summary>Состояние задачи</summary>
      <p id="task-state" class="task-state" role="status" aria-live="polite"></p>
      <ol id="task-stages" class="task-stages" aria-label="Этапы задачи"></ol>
      <form id="task-form" class="memory-controls">
        <label>Текущий шаг<textarea id="task-step" rows="3" maxlength="500" placeholder="Что выполняем сейчас"></textarea></label>
        <label>Ожидаемое действие<textarea id="task-expected" rows="3" maxlength="500" placeholder="Какой результат нужен следующим"></textarea></label>
        <button id="task-save" class="button secondary" type="submit">Сохранить шаг</button>
      </form>
      <div class="week-actions">
        <button id="task-advance" class="button primary" type="button">Следующий этап</button>
        <button id="task-pause" class="button secondary" type="button">Пауза</button>
        <button id="task-rework" class="button secondary" type="button">На доработку</button>
      </div>
      <p class="muted">Этап меняется только кнопкой. Пауза останавливает отправку сообщений и переходы; текущий шаг можно уточнять.</p>
    </details>
    <details id="invariants-panel" class="week-panel"><summary>Инварианты задачи</summary>
      <form id="invariants-form" class="memory-controls">
        <label>Язык решения<input id="invariant-language" maxlength="80" placeholder="Python"></label>
        <label>Архитектура<input id="invariant-architecture" maxlength="80" placeholder="Монолит"></label>
        <label>Предел бюджета<input id="invariant-budget" type="number" min="0" max="1000000000" step="1" placeholder="Без ограничения"></label>
        <button class="button secondary" type="submit">Сохранить инварианты</button>
      </form>
      <p class="muted">Пустое поле не ограничивает решение. Код проверяет язык, архитектуру и бюджет в полях решения. Смысл свободного текста и предпочтения профиля оценивает модель. Язык и архитектура сравниваются без учёта регистра, но без синонимов.</p>
      <details class="memory-details"><summary>Параметры следующего предложения</summary>
        <label class="proposal-toggle"><input id="proposal-enabled" type="checkbox">Передать вместе с сообщением</label>
        <div id="proposal-fields" class="memory-controls" hidden>
          <label>Язык предложения<input id="proposal-language" maxlength="80" placeholder="Python"></label>
          <label>Архитектура предложения<input id="proposal-architecture" maxlength="80" placeholder="Монолит"></label>
          <label>Бюджет предложения<input id="proposal-budget" type="number" min="0" max="1000000000" step="1"></label>
        </div>
      </details>
      <div class="check-result"><h3>Последняя проверка</h3><p id="invariant-check" role="status" aria-live="polite">Проверок пока нет.</p><p id="checked-proposal" class="muted"></p></div>
    </details>`;
  Object.assign(elements, Object.fromEntries([...elements["week-panels"].querySelectorAll("[id]")].map((node) => [node.id, node])));
  ["layers", "profiles", "task", "invariants"].forEach((name, index) => {
    elements[name + "-panel"].hidden = weekDay < 11 + index;
    elements[name + "-panel"].open = weekDay === 11 + index;
  });
  for (const [form, field, layer] of [["short-memory-form", "short-memory", "short_term"], ["working-memory-form", "working-memory", "working"], ["long-memory-form", "long-memory", "long_term"]]) {
    elements[form].addEventListener("submit", (event) => {
      event.preventDefault();
      let entries;
      try { entries = parseMemory(elements[field].value); } catch (error) { setWeekError(error.message); elements[field].focus(); return; }
      mutateWeek(layer === "long_term" ? "/api/memory" : chatPath(state.activeChatId) + "/memory", "PATCH",
        layer === "long_term" ? {entries} : {layer, entries}, "Память сохранена.", layer === "long_term");
    });
  }
  elements["profile-select"].addEventListener("change", renderProfileEditor);
  elements["profile-select-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    mutateWeek(chatPath(state.activeChatId), "PATCH", {profile_id: elements["profile-select"].value || null}, "Профиль применён.");
  });
  elements["profile-editor"].addEventListener("submit", (event) => { event.preventDefault(); saveProfile(false); });
  elements["profile-create"].addEventListener("click", () => saveProfile(true));
  elements["profile-delete"].addEventListener("click", () => {
    const id = elements["profile-select"].value;
    if (id && confirm("Удалить профиль? Он будет отключён во всех чатах.")) mutateWeek("/api/profiles/" + encodeURIComponent(id), "DELETE", undefined, "Профиль удалён.", true);
  });
  elements["task-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    mutateWeek(chatPath(state.activeChatId) + "/task", "PATCH", {action: "update", current_step: elements["task-step"].value.trim(), expected_action: elements["task-expected"].value.trim()}, "Шаг сохранён.");
  });
  for (const action of ["advance", "pause", "rework"]) elements["task-" + action].addEventListener("click", () => {
    mutateWeek(chatPath(state.activeChatId) + "/task", "PATCH", {action: action === "pause" && state.chat.task.paused ? "resume" : action}, "Состояние задачи сохранено.");
  });
  elements["invariants-form"].addEventListener("submit", (event) => {
    event.preventDefault();
    mutateWeek(chatPath(state.activeChatId) + "/invariants", "PATCH", {
      language: elements["invariant-language"].value.trim(), architecture: elements["invariant-architecture"].value.trim(),
      max_budget: elements["invariant-budget"].value === "" ? null : Number(elements["invariant-budget"].value),
    }, "Инварианты сохранены.");
  });
  elements["proposal-enabled"].addEventListener("change", () => {
    elements["proposal-fields"].hidden = !elements["proposal-enabled"].checked;
  });
}

function parseMemory(text) {
  const entries = Object.create(null);
  for (const line of text.split("\n").filter((line) => line.trim())) {
    const separator = line.indexOf("=");
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim();
    if (separator < 1 || !key || !value || key.length > 60 || value.length > 240) throw new Error("Каждая запись: ключ = значение. Ключ — до 60, значение — до 240 символов.");
    if (Object.hasOwn(entries, key)) throw new Error("Ключ «" + key + "» повторяется. Оставь одну запись.");
    entries[key] = value;
  }
  if (Object.keys(entries).length > 12) throw new Error("В одном слое допускается до 12 записей.");
  return entries;
}

function syncWeekFields(node, value, fill) {
  const signature = JSON.stringify([state.activeChatId, value]);
  if (node.dataset.snapshot === signature) return;
  node.dataset.snapshot = signature;
  fill();
}

function renderWeek(chat) {
  if (weekChatId !== chat.id) {
    weekChatId = chat.id;
    setWeekError();
    elements["week-status"].textContent = "";
    elements["proposal-enabled"].checked = false;
    elements["proposal-fields"].hidden = true;
    for (const field of ["language", "architecture", "budget"]) elements["proposal-" + field].value = "";
  }
  for (const [field, layer] of [["short-memory", "short_term"], ["working-memory", "working"], ["long-memory", "long_term"]]) {
    const entries = chat.memory?.[layer] || {};
    syncWeekFields(elements[field], entries, () => { elements[field].value = Object.entries(entries).map(([key, value]) => key + " = " + value).join("\n"); });
  }
  if (weekDay >= 12) syncWeekFields(elements["profile-select"], [chat.profile_id, state.profiles], () => {
    const options = [{id: "", name: "Без профиля"}, ...state.profiles].map((profile) => {
      const option = document.createElement("option"); option.value = profile.id; option.textContent = profile.name; return option;
    });
    elements["profile-select"].replaceChildren(...options);
    elements["profile-select"].value = chat.profile_id || "";
    renderProfileEditor();
  });
  if (weekDay >= 13 && chat.task) {
    const task = chat.task;
    elements["task-state"].textContent = (task.paused ? "На паузе · " : "") + taskStages[task.stage];
    elements["task-stages"].replaceChildren(...Object.entries(taskStages).map(([stage, label]) => {
      const item = document.createElement("li"); item.textContent = label;
      if (stage === task.stage) item.setAttribute("aria-current", "step"); return item;
    }));
    syncWeekFields(elements["task-form"], [task.current_step, task.expected_action], () => {
      elements["task-step"].value = task.current_step;
      elements["task-expected"].value = task.expected_action;
    });
    elements["task-pause"].textContent = task.paused ? "Продолжить задачу" : "Пауза";
    const next = {planning: "К выполнению", execution: "К проверке", validation: "Завершить", done: "Завершено"};
    elements["task-advance"].textContent = next[task.stage];
  }
  if (weekDay >= 14) {
    const limits = chat.invariants || {};
    syncWeekFields(elements["invariants-form"], limits, () => {
      elements["invariant-language"].value = limits.language || "";
      elements["invariant-architecture"].value = limits.architecture || "";
      elements["invariant-budget"].value = limits.max_budget ?? "";
    });
    const check = chat.last_check;
    elements["invariant-check"].textContent = check ? (check.status === "passed" ? "Пройдено. " : "Отклонено. ") + check.explanation : "Проверок пока нет.";
    elements["checked-proposal"].textContent = check?.proposal ? "Проверено: " + [check.proposal.language, check.proposal.architecture, "бюджет " + check.proposal.budget].join(" · ") : "";
  }
}

function renderProfileEditor() {
  const profile = state.profiles.find((item) => item.id === elements["profile-select"].value);
  for (const field of ["name", "style", "format", "constraints"]) elements["profile-" + field].value = profile?.[field] || "";
  updateControls();
}

function saveProfile(create) {
  if (!elements["profile-editor"].reportValidity()) return;
  const id = elements["profile-select"].value;
  if (!create && !id) return;
  const profile = Object.fromEntries(["name", "style", "format", "constraints"].map((field) => [field, elements["profile-" + field].value.trim()]));
  mutateWeek(create ? "/api/profiles" : "/api/profiles/" + encodeURIComponent(id), create ? "POST" : "PATCH", profile,
    create ? "Профиль создан. Выбери его в списке и примени к чату." : "Профиль сохранён.", true);
}

function updateWeekControls(locked) {
  elements["week-panels"].hidden = !state.chat || state.loadingChat;
  elements["week-panels"].querySelectorAll("input, textarea, select, button").forEach((node) => { node.disabled = locked; });
  const hasProfile = Boolean(elements["profile-select"].value);
  elements["profile-save"].disabled = locked || !hasProfile;
  elements["profile-delete"].disabled = locked || !hasProfile;
  const task = state.chat?.task;
  elements["task-paused-hint"].hidden = !task?.paused;
  if (task?.paused) {
    elements.send.disabled = true;
    elements.send.setAttribute("aria-label", "Отправка недоступна: задача на паузе");
  }
  const taskLocked = locked || !task || task.paused || task.stage === "done";
  elements["task-advance"].disabled = taskLocked;
  elements["task-save"].disabled = locked || !task;
  elements["task-step"].disabled = locked || !task;
  elements["task-expected"].disabled = locked || !task;
  elements["task-rework"].disabled = taskLocked || task?.stage !== "validation";
  elements["task-pause"].disabled = locked || !task;
}

async function mutateWeek(path, method, data, success, global = false) {
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend || state.loadingChat || !state.chat) return;
  const chatId = state.activeChatId;
  state.pendingOperation = "week";
  setWeekError();
  elements["week-status"].textContent = "Сохраняю…";
  updateControls();
  try {
    const result = await request(path, method, data);
    if (result.profiles) state.profiles = result.profiles;
    if (global) {
      if (state.activeChatId) await selectChat(state.activeChatId, false, true);
    } else if (result.chat) {
      upsertChat(result.chat);
      if (state.activeChatId === chatId) {
        ++state.selectionVersion;
        state.loadingChat = false;
        renderChat(result.chat);
      }
    }
    elements["week-status"].textContent = success;
  } catch (error) {
    setWeekError(error.message);
    elements["week-status"].textContent = "Не сохранено. Значения в форме сохранены для повтора.";
    if (error.code === "network") {
      state.synchronized = false;
      elements["week-status"].textContent = "Результат неизвестен. Обнови чаты перед повтором.";
    }
    if (error.code === "busy") state.serverBusy = true;
  } finally {
    state.pendingOperation = null;
    updateControls();
  }
}

function readProposal() {
  if (weekDay < 14 || !elements["proposal-enabled"].checked) return null;
  const language = elements["proposal-language"].value.trim();
  const architecture = elements["proposal-architecture"].value.trim();
  const raw = elements["proposal-budget"].value;
  const budget = Number(raw);
  if (!language || !architecture || raw === "" || !Number.isInteger(budget) || budget < 0 || budget > 1000000000) {
    throw new Error("Для предложения укажи язык, архитектуру и целый бюджет от 0 до 1 000 000 000.");
  }
  return {language, architecture, budget};
}
