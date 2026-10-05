# E2E Scenario: Pitch Agent Web

Платформы: Backend, Web

## Шаги

- [x] 1. Запустить локальный сервер и открыть `http://127.0.0.1:<port>` в новом Edge context; страница загружается без ошибок, начальная форма доступна. ✅ Edge, порт 18762, новая cookie-сессия; console/page errors отсутствуют.
- [x] 2. Ввести трек `Astin Ray, VAVA — TAKIPARIO` и описание; отправить форму; появляется ответ агента, реальные модель/сообщения/токены, повторная отправка блокируется во время ожидания. ✅ Реальный DeepSeek: deepseek-v4-flash, 148 токенов, 2 сообщения, 1 POST; кнопка disabled во время ожидания.
- [x] 3. Отправить уточнение `Сделай короче`; новый ответ появляется в том же диалоге, история и счётчик сообщений увеличиваются. ✅ 4 сообщения, история backend сохранена; provider stub для детерминированного продолжения.
- [x] 4. Перезагрузить страницу; трек, история и статистика восстанавливаются из cookie-сессии. ✅ Название, весь текст диалога и статистика идентичны; cookie HttpOnly.
- [x] 5. Проверить безопасный вывод ответа с HTML-подобным текстом; строка отображается буквально, DOM-элемент из ответа не создаётся. ✅ Provider stub: img/onerror/script отображаются как текст; #injected не существует.
- [x] 6. Смоделировать ошибку API; черновик уточнения и предыдущая история сохраняются, показана понятная ошибка, повтор не отправляется автоматически. ✅ Контролируемый provider 502; черновик и история идентичны, один POST, сообщение «Не удалось получить ответ модели. Попробуйте ещё раз.»
- [x] 7. Скопировать ответ; кнопка показывает подтверждение. Открыть сброс, отменить через Escape, затем подтвердить; история очищается, фокус возвращается в название трека. ✅ «Скопировано»; Escape сохраняет 6 сообщений; подтверждение очищает историю, счётчик 0, activeElement — track-name.
- [x] 8. Проверить ширины 320, 375, 414 и 768 px; одна колонка, нет горизонтальной прокрутки и обрезанных/двухстрочных кнопок. ✅ DOM measurements и просмотр PNG: пустое/активное состояние и reset dialog; также 1280/1920 px. Overflow отсутствует, кнопки в одну строку; gate 49 OK.
- [x] 9. Пройти интерфейс клавиатурой; labels, focus rings, Ctrl+Enter и status/error announcements доступны. ✅ Tab → description → generate, Enter и Ctrl+Enter отправляют; focus ring solid 2px, у всех полей labels, status aria-live=polite, error role=alert. Page errors отсутствуют; единственная console error — ожидаемый mock 502 шага 6.

## Validation — остановка перед E2E

2026-09-07: `python -m unittest discover -s projects/week-2-task-1 -v` — 7/7 OK; `py_compile main.py web.py` и `node --check static/app.js` — OK. Отдельная сборка не нужна: vanilla HTML/CSS/JS.

По указанию оркестратора Validation остановлена при провале Hallmark gates до первого browser-действия:

- Gate 1: `static/tokens.css:19` — системный Segoe UI в display font.
- Gate 25: `static/styles.css:20,45,78` — max-width прозы 40ch, 42ch и 35ch при требовании 45–75ch.
- Gate 39: `static/styles.css:23,27` — нет зарезервированного прозрачного outline у полей; disabled-состояние не содержит требуемую opacity. Глобальный outline-offset 3px вместо указанного для полей 1px.

Gate 48 проверен: цвета и font-family потребляют именованные tokens. Gate 49 требует runtime; ещё не проверен. E2E 1–9 не выполнялись, реальных API-вызовов не было. Production-файлы не менялись.

## Validation — повтор после CSS-исправлений

2026-09-07: повторно 7/7 unit tests, Python compile, JS syntax — OK. CSS gates 1/25/26/39/48 — OK после исправлений.

Шаг 1 начат через Playwright `chromium.launch({channel: 'msedge'})`, новый изолированный context. Страница и `/api/session` загружаются; начальная форма доступна. Проверка console остановила Validation: `Failed to load resource: the server responded with a status of 404 (Not Found)` — браузерный favicon отсутствует в HTML и allowlist сервера. Шаг 1 не отмечен, поскольку его условие «без ошибок» не выполнено. Шаги 2–9 не начаты, DeepSeek не вызывался. Context/browser закрыты. Требуется favicon и повтор шага 1.

## Validation — итог после favicon-исправления

2026-09-07: все 9 E2E-шагов пройдены. Первый ответ — настоящий DeepSeek API (148 токенов), последующие ответы и failure path — локальный provider stub при настоящих frontend/backend/session. Для дополнительных layout-состояний API-сессия подменена в отдельном Edge context. Скриншоты просмотрены. Личных browser-профилей не использовали; production-файлы Validation не изменяла. Исторические остановки выше устранены.
