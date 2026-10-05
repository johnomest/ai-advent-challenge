# E2E Scenario: Week 2 Day 3 — token metrics

Платформы: Backend, Web

## Шаги

- [x] 1. Запустить `week-2-task-3` с изолированной временной SQLite БД и mock DeepSeek; проверить успешный health/read API. ✅ GET `/api/chats` и `/` — 200; временная БД, локальный mock без внешнего API.
- [x] 2. Открыть GOOST CHAT в Edge при 1280×800; проверить бренд, TT Wellingtons, чат и блок «Токены и стоимость» без горизонтального скролла. ✅ После Fix scrollTop=0; заголовок целиком внутри transcript (y=254–297, transcript=94–422); `token-desktop-fixed.png`. До Fix TT Wellingtons и scrollWidth=1280 проверены.
- [x] 3. Выбрать «Короткий»; проверить, что заполняется черновик, live preview показывает оценку запроса/истории и отправка не происходит автоматически. ✅ Черновик 41 символ, запрос ≈20, история ≈0, сообщений 0. Действие выполнено до обнаружения дефекта на screenshot.
- [x] 4. Отправить короткий запрос; проверить ответ, фактические API input/output, стоимость и одну сохранённую строку истории метрик. ✅ HTTP 200, 2 сообщения, API input=99/output=24/total=123; USD 0.00003762–0.00007524; UI и GET показывают одну сохранённую строку.
- [x] 5. Выбрать и дважды отправить «Длинный»; проверить рост history/prompt/API total и стоимости между ходами. ✅ История 45→486, prompt 519→968, суммарные API tokens 687→1692; стоимость следующего хода выросла.
- [x] 6. Выбрать «Переполнение» и отправить; проверить HTTP 422/context_limit, сохранённый черновик, отсутствие нового сообщения/стоимости и доступную кнопку отправки. ✅ 422/context_limit; черновик сохранён, send enabled; сообщения, turn_metrics и total_tokens не изменились.
- [x] 7. Обновить страницу; проверить восстановление диалога и метрик без повторного начисления. ✅ Reload восстановил 6 сообщений, 3 строки метрик, total=1692 без изменений.
- [x] 8. Создать второй чат и переключаться между чатами при задержанном token-preview; проверить, что поздний ответ preview не переносит метрики в другой чат. ✅ Реальный ответ preview первого чата задержан Playwright route; после переключения поздний ответ не изменил preview/пустой черновик второго чата.
- [x] 9. Проверить `<details>`, preset-кнопки, textarea и отправку клавиатурой; фокус видим, labels доступны. ✅ Enter/Space переключают details; preset активируется Enter; Shift+Enter добавляет строку, Enter отправляет; Tab→send→Space отправляет. Все проверенные focus-visible имеют немедленный 2px outline; label/aria-describedby доступны.
- [x] 10. Проверить ширины 320, 375, 414 и 768 px: нет горизонтального скролла страницы, controls не обрезаны, текст кнопок не переносится, таблица прокручивается только внутри своей области. ✅ Все четыре viewport проверены визуально и по геометрии; root/body scrollWidth=viewport, overflow-x:clip. Таблица 250/305/344→672 px на телефонах, при 768 помещается; ArrowRight прокручивает только таблицу (40px), root=0, focus-visible 2px. `token-mobile-{320,375,414,768}.png`.
- [x] 11. Выполнить backend unittest, `py_compile`, `node --check`, `git diff --check`; проверить отсутствие secrets, БД и пользовательских данных в изменениях. ✅ 26/26 unittest; финальные py_compile/node/diff и whitespace всех 9 текстовых файлов относительно day 7 — PASS. 14 Git-кандидатов, 0 secret-pattern matches, 0 БД/ключей/логов/видео/pyc.

## Validation: PASS 2026-09-09

Первый дефект исправлен: `renderChat` прокручивает пустой чат к началу; шаг 2 повторно пройден.

Второй дефект исправлен: `static/index.html:70` теперь объясняет диапазон тарифами off-peak и peak и неизвестным точным моментом биллинга. Исправление проверено в Edge.

Команды: `python -m unittest discover -v` — 26/26 OK (10.593s); после последнего Fix `python -m py_compile main.py web.py test_main.py test_web.py`, `node --check static/app.js`, `git diff --check` — exit 0. Дополнительно `git -c core.autocrlf=false diff --no-index --check` для 9 изменённых текстовых файлов day 7→day 8 — без whitespace diagnostics. Backend после unittest не менялся.

Hallmark, применимые gates: PASS. Workbench/бренд сохранены по запросу; нет нового hero/footer/enrichment, поэтому их gates и diversification не применялись. Цвета/шрифты в CSS используют токены; нет transition-all, layout-анимаций, градиентного текста, italic headers, декоративного UI chrome или придуманных продуктовых метрик. Мобильные gates и keyboard/focus проверены в шагах 9–10. Native details/meter используются без лишней имитации.

Контраст вычислен в Edge по sRGB из computed CSS: 62 текстовых/icon элементов, 0 failures; минимум 5.8209:1. Дополнительно 11 семантических пар, включая muted на трёх поверхностях, error и primary default/hover/pressed; минимум текста 5.8209:1, focus на paper/surface 7.9711/6.9770:1. `prefers-reduced-motion: reduce`: transition=0s, active transform=none, animation сведена к opacity за 100ms. JS page errors=0.

Secret/data scan: 14 файлов новой задачи; 0 secret-pattern matches, 0 БД/ключей/логов/видео/pyc в Git-кандидатах. Тестовые SQLite БД изолированы в TemporaryDirectory и очищены после проверки. Edge contexts/browser закрыты. Временные validation helpers удалены; screenshots содержат только тестовые запросы.

Ограничение проверки: ответы DeepSeek подменялись локальным детерминированным mock; внешний API и фактический биллинг не вызывались.
