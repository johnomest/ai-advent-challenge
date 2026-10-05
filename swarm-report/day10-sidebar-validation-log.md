# Validation: правый инспектор и начало сообщений

Дата: 2026-09-12. Итоговый статус: PASS после двух исправлений фокуса при resize. История остановок сохранена ниже.

Среда: Microsoft Edge через Playwright `chromium.launch({channel:'msedge', headless:true})`; отдельные новые контексты. Сервер `day10-validation-server.py`, mock provider и временная SQLite. Production-файлы не изменялись.

## Пройдено

- `node --check projects/week-2-task-5/static/app.js`.
- 1440×1000: sidebar 272px, центр 832px, inspector 335px. Все технические элементы внутри inspector, в workspace их нет. Горизонтального переполнения нет.
- Тёмные баблы: user OKLCH L=0.309; assistant L=0.274. Подписи «Ты», «Ты · отправляется», «GOOST» видимы.
- Начала короткого user, короткого assistant, длинного user, длинного assistant: 15.97–16.02px от верха transcript. Длинный ответ 2349px при transcript 717px.
- Preview и обычный sync сохраняют scrollTop=85px, включая preview с предупреждением о превышении контекста.
- Переключение чата при pending: завершение ответа в другом чате сохраняет scrollTop=95px активного.
- Ошибка HTTP 400: временный бабл удалён, черновик сохранён. Успешный POST с потерянным ответом: recovery даёт ровно один user и один assistant, без временного дубля; черновик очищен.
- Branching: выбран ход 1 из двух справа; созданы A/B с первыми двумя сообщениями.
- 1280×800: центр 672px, inspector 335px, переполнения нет; короткий/длинный user/assistant открываются с начала, 15.97–16.02px.
- 1100×800: inspector в правом dialog, начальный фокус close-inspector; Escape и backdrop закрывают, фокус возвращается на opener. Native dialog допускает проход через UI браузера при Shift+Tab (document.hasFocus=false), затем возвращает в dialog; элементы фоновой страницы не фокусируются.

## Дефект

1. Открыть приложение на 1100×800.
2. Нажать «Открыть настройки и метрики».
3. Проверить `document.activeElement.id === 'close-inspector'`.
4. Изменить размер на 1440×1000.
5. Фактически: `document.activeElement.tagName === 'BODY'`, id пустой. Вкладка имеет фокус. Inspector в inspector-host; dialog закрыт; sync доступен. Ожидается фокус на доступном контроле inspector, как предусмотрено placeInspector.

Повторено дважды. Production не исправлялся. Остановлена Validation. 390×844 и 320×700 не запускались. Продолжать после исправления с незавершённой части шага 8 сценария.

Скриншоты: `day10-sidebar-1440-initial.png`, `day10-sidebar-1440-long.png`, `day10-sidebar-1440-branches.png`, `day10-sidebar-1280-long.png`, `day10-sidebar-1100-inspector.png`, `day10-sidebar-resize-focus-defect.png`.

Проверка использовала существующие зависимости и mock server. Два уточнения тестового ожидания: preview может завершаться предупреждением контекста; native dialog может временно отдавать фокус интерфейсу браузера. Это не дефекты приложения.

Cleanup: pageerror отсутствуют; контекст и Edge закрыты; сервер остановлен; процесс mock server отсутствует. Все пройденные шаги сохранены в `day10-sidebar-e2e-scenario.md`.

## Повторная Validation после первого focus fix

`node --check` PASS. Пройденные шаги 1–7 не повторялись. Новый отдельный Edge context начал на 1100×800.

- Прямой resize 1100→1440 исправлен: close-inspector → sync, панель перенесена, dialog закрыт.
- Обратный resize 1440→1100 не исправлен: исходный activeElement.id=sync; после viewport resize activeElement=BODY, document.hasFocus=true; inspector в inspector-drawer, dialog закрыт, open-inspector видим (display:flex). Ожидается фокус на open-inspector.
- Скриншот `day10-sidebar-resize-reverse-focus-defect.png`.
- Validation остановлена на шаге 8; 390/320 ещё не запускались. Вероятный механизм: CSS скрывает inspector-host до проверки contains(document.activeElement).

## Финальная Validation после focus-owner fix

- `node --check projects/week-2-task-5/static/app.js` — PASS. Шаги 1–7 не повторялись.
- Resize правой панели в обе стороны — PASS: close-inspector → sync → open-inspector. Левая панель — PASS: close-drawer → new-chat → open-drawer.
- 390×844 — обе панели в отдельных dialog, одновременно не открываются. Начальный фокус на закрытии; Tab внутри inspector; Escape/backdrop закрывают, возвращают фокус opener. Горизонтального переполнения нет (scrollWidth=390). Центр не содержит технические элементы.
- 390×844 — короткий/длинный user + assistant начинаются на 15.56–16.08px. Длинный assistant 4550px, transcript 529px.
- 320×700 — правый inspector 304px, x=16; кнопки доступны, фокус возвращается. scrollWidth=320. Короткий/длинный user + assistant начинаются на 15.67–16.00px. Длинный assistant 4576px, transcript 385px.
- Скриншоты `day10-sidebar-390-inspector.png`, `day10-sidebar-390-long.png`, `day10-sidebar-320-inspector.png`, `day10-sidebar-320-long.png` просмотрены: тёмные баблы, читаемые подписи, ввод и панели без горизонтального обрезания.
- Pageerror=0. Контексты/Edge закрыты, сервер завершён; процесс mock server отсутствует.
- Все 11 шагов сценария пройдены. Изменений production в Validation нет.
