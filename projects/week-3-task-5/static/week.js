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
      <p id="task-state" class="task-state" role="status" aria-live="polite" tabindex="-1"></p>
      <p id="task-current-action" class="muted"></p>
      <ol id="task-stages" class="task-stages" aria-label="Этапы задачи"></ol>
      <p id="task-allowed" class="muted"></p>
      <form id="task-transition-form" class="memory-controls">
        <label>Перейти к этапу<select id="task-target" aria-describedby="task-transition-hint">
          <option value="planning">Планирование</option><option value="execution">Выполнение</option>
          <option value="validation">Проверка</option><option value="done">Завершено</option>
        </select></label>
        <p id="task-transition-hint" class="muted">Выбери этап. Сервер проверит условия перехода.</p>
        <button id="task-transition" class="button primary" type="submit">Перейти</button>
      </form>
      <button id="task-pause" class="button secondary" type="button">Пауза</button>
      <p class="muted">Пауза блокирует сообщения и изменения задачи. «Завершено» — конечный этап.</p>
      <form id="task-plan-form" class="memory-controls">
        <label>План<textarea id="task-plan" rows="4" maxlength="16000" placeholder="Шаги и критерии готовности"></textarea></label>
        <p id="task-plan-status" class="muted"></p>
        <button id="task-plan-save" class="button secondary" type="submit">Сохранить план</button>
        <button id="task-plan-approve" class="button secondary" type="button">Утвердить сохранённый план</button>
      </form>
      <form id="task-execution-form" class="memory-controls">
        <label>Результат выполнения<textarea id="task-execution" rows="4" maxlength="16000" placeholder="Что выполнено по плану"></textarea></label>
        <button id="task-execution-save" class="button secondary" type="submit">Сохранить результат</button>
      </form>
      <form id="task-validation-form" class="memory-controls">
        <p id="task-validation-summary" class="muted"></p>
        <label>Результат проверки<select id="task-validation-status"><option value="passed">Пройдена</option><option value="failed">Не пройдена</option></select></label>
        <label>Отчёт проверки<textarea id="task-validation-report" rows="3" maxlength="16000" placeholder="Проверенные критерии и замечания"></textarea></label>
        <button id="task-validation-save" class="button secondary" type="submit">Сохранить проверку</button>
      </form>
      <details class="memory-details"><summary>Текущий шаг и действие</summary>
      <form id="task-form" class="memory-controls">
        <label>Текущий шаг<textarea id="task-step" rows="3" maxlength="500" placeholder="Что выполняем сейчас"></textarea></label>
        <label>Ожидаемое действие<textarea id="task-expected" rows="3" maxlength="500" placeholder="Какой результат нужен следующим"></textarea></label>
        <button id="task-save" class="button secondary" type="submit">Сохранить шаг</button>
      </form>
      </details>
      <details class="memory-details"><summary>История изменений</summary><ol id="task-history" class="task-history"></ol></details>
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
  elements["task-panel"].open = true;
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
    mutateTask("update", {current_step: elements["task-step"].value.trim(), expected_action: elements["task-expected"].value.trim()});
  });
  elements["task-transition-form"].addEventListener("submit", (event) => {
    event.preventDefault(); mutateTask("transition", {target_stage: elements["task-target"].value});
  });
  elements["task-target"].addEventListener("change", renderTransitionHint);
  elements["task-pause"].addEventListener("click", () => mutateTask(state.chat?.task?.paused ? "resume" : "pause"));
  elements["task-plan-form"].addEventListener("submit", (event) => {
    event.preventDefault(); mutateTask("save_plan", {plan: elements["task-plan"].value.trim()});
  });
  elements["task-plan"].addEventListener("input", () => updateControls());
  elements["task-plan-approve"].addEventListener("click", () => mutateTask("approve_plan"));
  elements["task-execution-form"].addEventListener("submit", (event) => {
    event.preventDefault(); mutateTask("save_execution", {execution_result: elements["task-execution"].value.trim()});
  });
  elements["task-validation-form"].addEventListener("submit", (event) => {
    event.preventDefault(); mutateTask("save_validation", {status: elements["task-validation-status"].value, report: elements["task-validation-report"].value.trim()});
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

function syncTaskField(id, value) {
  const node = elements[id];
  // Keep edits when a newer server revision arrives, including conflict recovery.
  if (node.dataset.chatId !== state.activeChatId || node.value === node.dataset.serverValue) node.value = value;
  node.dataset.chatId = state.activeChatId;
  node.dataset.serverValue = value;
}

function renderTransitionHint() {
  const task = state.chat?.task;
  const target = elements["task-target"].value;
  elements["task-transition-hint"].textContent = task?.transition_reasons?.[target]
    || (task?.allowed_transitions?.includes(target) ? "Переход разрешён." : "Выбери этап. Сервер проверит условия перехода.");
}

function mutateTask(action, fields = {}) {
  if (!state.chat?.task) return;
  return mutateWeek(chatPath(state.activeChatId) + "/task", "PATCH",
    {action, expected_revision: state.chat.task.revision, ...fields}, "Состояние задачи сохранено.");
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
    elements["task-state"].textContent = (task.paused ? "На паузе · " : "") + taskStages[task.stage] + " · ревизия " + task.revision;
    elements["task-current-action"].textContent = "Текущий шаг: " + (task.current_step || "не указан") + ". Ожидаемое действие: " + (task.expected_action || "не указано");
    elements["task-stages"].replaceChildren(...Object.entries(taskStages).map(([stage, label]) => {
      const item = document.createElement("li"); item.textContent = label;
      if (stage === task.stage) item.setAttribute("aria-current", "step"); return item;
    }));
    for (const [id, value] of [["task-step", task.current_step], ["task-expected", task.expected_action],
      ["task-plan", task.plan], ["task-execution", task.execution_result],
      ["task-validation-status", task.validation?.status || "passed"], ["task-validation-report", task.validation?.report || ""]]) syncTaskField(id, value);
    elements["task-allowed"].textContent = "Доступные переходы: " + (task.allowed_transitions.map((stage) => taskStages[stage]).join(", ") || "нет");
    elements["task-plan-status"].textContent = task.plan_approved ? "Сохранённый план утверждён." : task.plan ? "План сохранён, ожидает утверждения." : "План пока не сохранён.";
    elements["task-validation-summary"].textContent = task.validation ? "Сохранённая проверка: " + (task.validation.status === "passed" ? "пройдена." : "не пройдена.") : "Проверки пока нет.";
    elements["task-pause"].textContent = task.paused ? "Продолжить задачу" : "Пауза";
    syncWeekFields(elements["task-target"], task.stage, () => {
      elements["task-target"].value = {planning: "execution", execution: "validation", validation: "done", done: "done"}[task.stage];
    });
    renderTransitionHint();
    const actions = {transition: "Переход", update: "Шаг обновлён", save_plan: "План сохранён", approve_plan: "План утверждён", save_execution: "Результат сохранён", save_validation: "Проверка сохранена", pause: "Пауза", resume: "Продолжение"};
    const history = task.history.slice().reverse().map((entry) => {
      const item = document.createElement("li");
      item.textContent = "#" + entry.revision + " · " + (actions[entry.action] || entry.action) + " · " + taskStages[entry.from_stage]
        + (entry.from_stage === entry.to_stage ? "" : " → " + taskStages[entry.to_stage]);
      return item;
    });
    if (!history.length) { const item = document.createElement("li"); item.textContent = "Изменений пока нет."; history.push(item); }
    elements["task-history"].replaceChildren(...history);
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
  const terminal = task?.stage === "done";
  elements["task-paused-hint"].hidden = !task?.paused && !terminal;
  elements["task-paused-hint"].textContent = terminal ? "Задача завершена. Для новой задачи создай чат." : "Задача на паузе. Нажми «Продолжить задачу» в панели состояния.";
  if (task?.paused || terminal) {
    elements.send.disabled = true;
    elements.send.setAttribute("aria-label", terminal ? "Отправка недоступна: задача завершена" : "Отправка недоступна: задача на паузе");
  }
  const taskLocked = locked || !task || task.paused || terminal;
  for (const id of ["task-transition", "task-target", "task-save", "task-step", "task-expected"]) elements[id].disabled = taskLocked;
  for (const [prefix, stage] of [["plan", "planning"], ["execution", "execution"], ["validation", "validation"]]) {
    elements["task-" + prefix + "-form"].querySelectorAll("textarea, select, button").forEach((node) => { node.disabled = taskLocked || task?.stage !== stage; });
  }
  elements["task-plan-approve"].disabled ||= !task?.plan || task.plan_approved || elements["task-plan"].value.trim() !== task.plan;
  elements["task-pause"].disabled = locked || !task || terminal;
}

async function mutateWeek(path, method, data, success, global = false) {
  if (state.pendingOperation || state.serverBusy || !state.synchronized || state.uncertainSend || state.loadingChat || !state.chat) return;
  const chatId = state.activeChatId;
  const version = state.selectionVersion;
  const opener = document.activeElement;
  const isCurrent = () => state.activeChatId === chatId && state.selectionVersion === version;
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
      if (isCurrent()) {
        state.loadingChat = false;
        renderChat(result.chat);
      }
    }
    if (isCurrent() || (global && state.activeChatId === chatId)) elements["week-status"].textContent = success;
  } catch (error) {
    if (isCurrent()) {
      setWeekError(error.message);
      elements["week-status"].textContent = "Не сохранено. Значения в форме сохранены для повтора.";
    }
    if (error.code === "stale_revision" && isCurrent()) {
      try {
        const latest = await request(chatPath(chatId));
        upsertChat(latest.chat);
        if (isCurrent()) {
          state.serverBusy = Boolean(latest.chat.busy);
          renderChat(latest.chat);
          elements["week-status"].textContent = "Состояние обновлено с сервера. Черновики сохранены; проверь их перед повтором.";
        }
      } catch (reloadError) {
        if (isCurrent()) {
          state.synchronized = false;
          setWeekError(reloadError.message);
          elements["week-status"].textContent = "Не удалось обновить состояние. Черновики сохранены. Обнови чаты перед повтором.";
        }
      }
    }
    if (error.code === "network") {
      state.synchronized = false;
      if (isCurrent()) elements["week-status"].textContent = "Результат неизвестен. Обнови чаты перед повтором.";
    }
    if (error.code === "busy") state.serverBusy = true;
  } finally {
    state.pendingOperation = null;
    updateControls();
    if (isCurrent() && opener?.isConnected && document.activeElement === document.body) {
      (opener.disabled ? elements["task-state"] : opener).focus({preventScroll: true});
    }
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
