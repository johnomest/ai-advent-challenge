# E2E Scenario: GOOST CHAT

Платформы: Backend, Web. Validation: 2026-09-08.

## Шаги

- [x] 1. Запустить unit tests, JS syntax и static integrity; все проверки проходят. ✅ 15 tests, node --check, unique IDs/assets/no innerHTML.
- [x] 2. Поднять изолированный сервер с временной SQLite и локальным fake DeepSeek endpoint на портах, отличных от 8765; внешних model calls нет. ✅ App 7656, provider 7655, temp SQLite goost-validation-1f59g7s7.
- [x] 3. Desktop Edge, новый context: создать первый чат, отправить сообщение; ответ, заголовок и запись списка обновлены. ✅ 1440×1000, goost-desktop.png, page errors 0.
- [x] 4. Создать второй чат; проверить независимые черновики, rename, select, delete. ✅ A/B drafts preserved; second renamed; disposable third chat deleted.
- [x] 5. Задержать ответ A, перейти в B, набрать черновик; ответ A не заменяет B/черновик, в A ответ сохранён. ✅ Local provider delay 12s; B stayed empty, new B draft intact, A has second answer.
- [x] 6. Перезапустить приложение с той же временной SQLite и cookie; чаты, сообщения и заголовки восстановлены. ✅ Server closed/recreated, page reload: 2 chats, 4 A messages, renamed B restored.
- [x] 7. Во втором новом context GET/PATCH/DELETE/send к чужому chat_id возвращают одинаковый 404. ✅ New owner list empty; all four responses uniform 404/not_found/Чат не найден.
- [x] 8. Mobile Edge: отдельные contexts 320/375/414/768; overflow отсутствует, drawer open/close/Escape/focus return работают, controls >=44px, clickable labels не переносятся. ✅ All four fresh contexts PASS incl. manage dialog controls; screenshots goost-mobile-{width}.png; page errors 0.
- [x] 9. Клавиатура: видимый focus, Enter отправляет, Shift+Enter переносит строку, dialogs focus/cancel, copy feedback работают. ✅ 2px solid focus-visible; real clipboard read matches answer; rename input/delete cancel autofocus, Escape/cancel preserve data.
- [x] 10. Hallmark 58-gate slop test, contrast/token inspection: computed root/main #161C29, #0b0b0b отсутствует. ✅ Все58 gates оценены: применимые PASS, font user override; prose72ch, button line-height1/height44px, min text contrast5.836:1. Body/canvas/workspace#161C29, accent#FCBF40.

## Результаты

Все10 steps PASS. При повторных CSS-проверках steps1–9 не повторялись. Hallmark25/26/36/39 исправлены и проверены; colors/tokens/contrast PASS. См. goost-chat-validation.md. Browser/context/static server закрыты; можно переходить Validation → Report.
