# GOOST CHAT

Дата: 2026-09-08. Статус: **Done**.

## Задача

Переделать существующий чат в фирменный GOOST CHAT: dashboard со списком чатов слева и основным окном справа, на манер ChatGPT. Итоговая палитра: Dark Mode 900 `#161C29`, акцент `#FCBF40`, тёмные нейтральные градиенты. Шрифты — Bahnschrift + Segoe UI с поддержкой кириллицы; пользовательский скриншот шрифтов использован только как ориентир размеров.

## Research

Консилиум: архитектура, frontend, UI, API, security.

- Найдена потеря SQLite-истории при очистке idle-сессий: TTL удалял постоянные данные. Cookie ID одновременно служил conversation ID.
- Принято разделить `owner_id` и `chat_id`, оставить SQLite источником истины, исключить удаление истории при вытеснении из RAM. Добавить миграцию, проверку владельца и `request_id` для безопасных повторов.
- UI-концепция Workbench: боковая панель, мобильный drawer, независимые черновики, защита от запоздавших ответов, вывод через `textContent`.
- Границы безопасности: Host/Origin, JSON и размер тела, защищённые cookie, одинаковый 404 для чужих чатов. Ограничения публичного tunnel отражены в документации.
- Сохранён существующий стек: Python stdlib и vanilla JavaScript, без новых зависимостей.

## План

1. Реализовать хранение нескольких чатов, миграцию, CRUD/list/message API и backend-проверки.
2. Построить GOOST CHAT dashboard; связать API, черновики и состояния запросов.
3. Обновить брендовые tokens, README и `.hallmark`; проверить Backend/Web на изолированных данных.

Авторизация, streaming, выбор модели и cloud sync в объём задачи не входят.

## Реализация

Основной каталог: `D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2`.

- [main.py](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/main.py): SQLite multi-chat CRUD, атомарная миграция `PRAGMA user_version=1` с сохранением прежних диалогов; постоянная история не зависит от RAM-сессий.
- [web.py](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/web.py): отдельные случайные chat IDs, cookie `goost_owner` на год и fallback старого cookie; owner-scoped API. Одна мутация на владельца, чтение доступно во время генерации. `request_id` обрабатывает replay/conflict/pending, ошибки не оставляют частично записанную пару сообщений. Проверки Origin включают PATCH.
- [test_main.py](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/test_main.py), [test_web.py](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/test_web.py): 15 unit tests.
- [index.html](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/static/index.html), [app.js](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/static/app.js), [styles.css](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/static/styles.css): интерфейс на полную высоту, создание/выбор/переименование/удаление чатов, composer, мобильный modal drawer, копирование обычного текста. Черновики разделены по чатам; `selectionVersion` предотвращает подмену активного чата запоздавшим ответом. Добавлена синхронизация при неопределённом результате запроса.
- [README.md](/D:/Work/Projects/ai-advent-challenge/projects/week-2-task-2/README.md), `.hallmark`: документация, ограничения и решения визуальной системы.

## Validation

Платформы: **Backend, Web**. [Сценарий](/D:/Work/Projects/ai-advent-challenge/swarm-report/goost-chat-e2e-scenario.md): **10/10 выполнено**. [Подробный отчёт](/D:/Work/Projects/ai-advent-challenge/swarm-report/goost-chat-validation.md).

- 15 unit tests — PASS; `node --check` и static integrity — PASS.
- Изолированный сервер и локальный fake provider; `.env` не читался, внешних платных запросов не было. Пользовательский сервер не затронут.
- Edge: создание/отправка/title, CRUD и черновики, задержанный ответ A после перехода в B, сохранность истории после рестарта, одинаковые 404 для чужих IDs — PASS.
- Desktop 1440px и mobile 320/375/414/768px; overflow, drawer, клавиатура, focus, dialogs и реальный clipboard — PASS. Page errors: 0.
- Все 58 Hallmark gates оценены: применимые PASS, отсутствующие паттерны N/A, пользовательская типографика учтена как override. Открытых замечаний нет.
- Computed background `#161C29`, accent `#FCBF40`; `#0b0b0b` отсутствует. Минимальный контраст текста 5.836:1, accent ink 10.278:1. Ширина ответа 72ch, кнопки высотой 44px с `line-height: 1`.
- Browser contexts и тестовые серверы закрыты.

## Проблемы и откаты

Два перехода **Validation → Executing** для CSS: pressed-state `.chat-select`, стабильный outline/offset полей, ограничение ответа assistant до 72ch, `line-height: 1` кнопок. После исправлений повторно выполнялся только шаг 10; шаги 1–9 не повторялись. Все дефекты закрыты.

## Ограничения и завершение

- Поддерживается один локальный процесс сервера.
- История принадлежит браузерному cookie: его удаление лишает доступа к прежним чатам. Черновики не переживают перезагрузку страницы.
- Авторизации нет. Любой получивший публичный tunnel URL может вызывать платный API; URL сам по себе не является защитой доступа.
- Ответы выводятся обычным текстом, без Markdown.

**Статус: Done.** Реализация и применимые проверки завершены. Commit/push и завершение во внешних системах не выполнялись: `/done` или отдельного запроса на commit не было.
