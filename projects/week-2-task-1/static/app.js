"use strict";

const elements = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map((element) => [element.id, element]),
);
const fields = [elements["track-name"], elements.description, elements.message];
const hints = new Map(fields.map((field) => [field, {
  node: document.getElementById(field.getAttribute("aria-describedby")),
  text: document.getElementById(field.getAttribute("aria-describedby")).textContent,
}]));
let session = null;
let pending = false;
let synchronized = false;

function setStatus(message) {
  elements.status.textContent = message;
}

function setError(message = "") {
  elements.error.textContent = message;
  elements.error.hidden = !message;
}

function validate(field) {
  const hint = hints.get(field);
  const valid = Boolean(field.value.trim()) && field.value.length <= field.maxLength;
  field.setAttribute("aria-invalid", String(!valid));
  hint.node.classList.toggle("invalid", !valid);
  hint.node.textContent = valid ? hint.text : (
    field.value.trim() ? `Слишком длинный текст. Сократи до ${field.maxLength} символов.`
      : "Поле пустое. Добавь текст, чтобы отправить запрос."
  );
  return valid;
}

function updateControls() {
  const active = Boolean(session?.track);
  const locked = pending || !synchronized;
  elements.generate.disabled = locked || active;
  elements.generate.hidden = active;
  elements.generate.textContent = pending && !active ? "Готовлю питч…" : "Написать питч";
  for (const field of [elements["track-name"], elements.description]) {
    field.disabled = !synchronized;
    field.readOnly = pending || active;
  }
  elements.send.disabled = locked;
  elements.send.textContent = pending ? "Готовлю ответ…" : "Отправить";
  elements.reset.disabled = locked || !active;
  elements.sync.hidden = synchronized;
  elements.sync.disabled = pending;
  elements["message-form"].hidden = !active;
  elements.empty.hidden = Boolean(session?.messages.length);
  elements["track-form"].setAttribute("aria-busy", String(pending));
  elements["message-form"].setAttribute("aria-busy", String(pending));
  elements["track-status"].textContent = active
    ? "Трек закреплён за диалогом. Для другого трека начни новый."
    : "Первый вариант будет на английском.";
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
    });
    result = await response.json();
  } catch {
    throw new Error("Связь с сервером прервалась. Проверь, что он запущен, и повтори проверку связи.");
  }
  if (!response.ok) {
    const error = new Error(result.error?.message || "Не удалось выполнить запрос. Проверь связь с сервером.");
    error.code = result.error?.code;
    throw error;
  }
  return result;
}

function renderSession(next, animate = false) {
  const previousCount = session?.messages.length ?? 0;
  session = next;
  synchronized = true;
  if (next.track) {
    elements["track-name"].value = next.track.name;
    elements.description.value = next.track.description;
  }
  const fragment = document.createDocumentFragment();
  next.messages.forEach((message, index) => {
    const item = document.createElement("li");
    const assistant = message.role === "assistant";
    item.className = `message ${assistant ? "assistant" : "user"}`;
    if (animate && assistant && index >= previousCount) item.classList.add("new-answer");
    const header = document.createElement("div");
    header.className = "message-header";
    const author = document.createElement("span");
    author.className = "message-author";
    author.textContent = assistant ? "Pitch Agent" : "Ты";
    header.append(author);
    if (assistant) {
      const copy = document.createElement("button");
      copy.className = "button secondary copy";
      copy.type = "button";
      copy.textContent = "Скопировать";
      copy.setAttribute("aria-label", `Скопировать ответ ${Math.floor(index / 2) + 1}`);
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
          setStatus("Не удалось скопировать. Выдели текст ответа и скопируй вручную.");
        } finally {
          copy.disabled = false;
          setTimeout(() => {
            copy.textContent = "Скопировать";
            delete copy.dataset.state;
          }, 2500);
        }
      });
      header.append(copy);
    }
    const content = document.createElement("p");
    content.className = "message-content";
    content.textContent = index === 0 && next.track
      ? `${next.track.name}\n${next.track.description}` : message.content;
    item.append(header, content);
    fragment.append(item);
  });
  elements.messages.replaceChildren(fragment);
  elements.model.textContent = next.model;
  elements["message-count"].textContent = next.messages.length.toLocaleString("ru-RU");
  elements["token-count"].textContent = next.total_tokens.toLocaleString("ru-RU");
  updateControls();
}

async function synchronize() {
  if (pending) return;
  pending = true;
  updateControls();
  setError();
  setStatus("Проверяю диалог…");
  try {
    renderSession(await request("/api/session"));
    setStatus(session.track ? "Диалог восстановлен. Можно продолжать." : "Всё готово. Добавь данные трека.");
  } catch (error) {
    synchronized = false;
    setError(error.message);
    setStatus(error.code === "busy"
      ? "Ответ ещё готовится. Проверь диалог через несколько секунд."
      : "Связь не подтверждена. Проверь, что сервер запущен.");
  } finally {
    pending = false;
    updateControls();
  }
}

async function submit(formFields, payload) {
  if (pending || !synchronized) return;
  const invalid = formFields.map((field) => [field, validate(field)]).find(([, valid]) => !valid);
  if (invalid) {
    invalid[0].focus();
    return;
  }
  const draft = elements.message.value;
  pending = true;
  updateControls();
  setError();
  setStatus("Модель готовит ответ. Это может занять около минуты.");
  try {
    renderSession(await request("/api/messages", "POST", payload), true);
    if (elements.message.value === draft) elements.message.value = "";
    setStatus("Ответ готов. Можно продолжать диалог.");
    elements.message.focus({preventScroll: true});
    elements.messages.lastElementChild?.scrollIntoView({block: "nearest"});
  } catch (error) {
    // A lost response may still have committed. Read before allowing a retry.
    synchronized = false;
    setError(error.message);
    try {
      renderSession(await request("/api/session"));
      setStatus("Диалог проверен. Черновик сохранён — проверь сообщения перед повторной отправкой.");
    } catch {
      setStatus("Не удалось проверить результат. Черновик сохранён. Нажми «Проверить связь» перед повтором.");
    }
  } finally {
    pending = false;
    updateControls();
  }
}

fields.forEach((field) => {
  field.addEventListener("blur", () => {
    if (!field.disabled && !field.readOnly) validate(field);
  });
  field.addEventListener("input", () => {
    if (field.hasAttribute("aria-invalid")) validate(field);
  });
});
elements["track-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  submit([elements["track-name"], elements.description], {
    name: elements["track-name"].value.trim(), description: elements.description.value.trim(),
  });
});
elements["message-form"].addEventListener("submit", (event) => {
  event.preventDefault();
  submit([elements.message], {message: elements.message.value.trim()});
});
elements.message.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && !event.isComposing) {
    event.preventDefault();
    elements["message-form"].requestSubmit();
  }
});
elements.sync.addEventListener("click", synchronize);
elements.reset.addEventListener("click", () => elements["reset-dialog"].showModal());
elements["cancel-reset"].addEventListener("click", () => elements["reset-dialog"].close());
elements["confirm-reset"].addEventListener("click", async () => {
  if (pending || !synchronized) return;
  elements["reset-dialog"].close();
  pending = true;
  updateControls();
  setError();
  setStatus("Начинаю новый диалог…");
  try {
    renderSession(await request("/api/session", "DELETE", {}));
    elements["track-form"].reset();
    elements["message-form"].reset();
    fields.forEach((field) => {
      field.removeAttribute("aria-invalid");
      hints.get(field).node.classList.remove("invalid");
      hints.get(field).node.textContent = hints.get(field).text;
    });
    setStatus("Новый диалог готов. Добавь другой трек.");
  } catch (error) {
    synchronized = false;
    setError(error.message);
    setStatus("Не удалось подтвердить сброс. Проверь связь, чтобы узнать состояние диалога.");
  } finally {
    pending = false;
    updateControls();
    if (synchronized) elements["track-name"].focus();
  }
});
synchronize();
