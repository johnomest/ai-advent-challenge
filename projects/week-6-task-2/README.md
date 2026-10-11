# День 27 — простой локальный CLI-чат

Цель: встроить локальную LLM в приложение, которое принимает вопросы и показывает
ответы без облачной модели. Изучаем HTTP API Ollama и передачу истории диалога.

Реализация: Python, стандартная библиотека, Qwen3.5-9B-Q8_0 через llama.cpp.
Используется существующий GGUF из `models`, без импорта в Ollama и копии весов.
История только в RAM:
последние 5 пар сообщений; прошлые ответы ограничиваются 2000 символами. Новая
сессия не помнит предыдущую. Это небольшой чат, не долговременная память.

## Запуск из корня репозитория

В первом PowerShell-терминале запустить сервер:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/start-local-qwen.ps1
```

Скрипт использует измеренную сборку `llama.cpp b11514` из
`.local-archive/models-cleanup-20261011-3UZ0qB/llama-b11514-no-prefetch-cuda13.0/`.
Этот каталог с DLL и `models/Qwen3.5-9B-Q8_0/` должны оставаться доступными.
Сервер слушает только `127.0.0.1:8080`; CORS ограничен этим адресом.
Порт должен быть свободен; запущенные процессы скрипт не останавливает.

Во втором терминале из корня репозитория:

```powershell
.\.venv\Scripts\python.exe projects/week-6-task-2/main.py
```

Команды: `/reset` — очистить историю, `/exit` — выйти. Один вопрос:

```powershell
.\.venv\Scripts\python.exe projects/week-6-task-2/main.py --question "Объясни, что такое RAG, в двух предложениях."
```

Настройки: `--model`, `--url`, `--max-tokens` (по умолчанию 1536, максимум 4096).
Контекст сервера 8192, temperature 0, thinking отключён. При обрыве ответа выдаётся ошибка,
частичный текст не добавляется в историю. Ошибка сервера не закрывает чат.

Только loopback HTTP, без системного proxy и HTTP redirects. Перед запуском чат
проверяет наличие точного alias `Qwen3.5-9B-Q8_0` через `/v1/models`.
Ответы идут через `/v1/chat/completions`. Скрипт не читает `.env` и не скачивает
модели автоматически. Ollama для Дня 27 не нужна.

Документация HTTP API: [llama.cpp server](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md).

## Проверка

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s projects/week-6-task-2 -p "test_*.py"
```

На видео: запуск, обычный вопрос, запоминание имени/даты, follow-up, `/reset`,
проверка сброса и `/exit`. Подробно: `VIDEO-SCENARIO.md`.
