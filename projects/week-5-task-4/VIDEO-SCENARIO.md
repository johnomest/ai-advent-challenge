# День 24 — сценарий видео

## 1. Объяснить цель

«Проверяем не только ответ RAG, но и доказательства: откуда взят каждый факт,
есть ли точная цитата, соответствует ли ей ответ. Если контекст слабый — не знаю».

Терминал в корне репозитория, `.venv` активировано.

## 2. Ответ с важным исключением

```powershell
python projects/week-5-task-4/main.py --with-answers
```

Показать `ANSWER [answered]`, `SOURCES`, `QUOTES`.
Ожидание: Framestore смотрит на demo reel, а не образование; диплом может
понадобиться для рабочей визы. Не терять визовую оговорку.
В источнике — PDF page 13 / FRAMESTORE / chunk_id.
Сверить каждое утверждение с цитатой, привязанной через `claim=...`.

## 3. Другая студия

```powershell
python projects/week-5-task-4/main.py --question "Нужен ли студии IV отдельный resume или достаточно portfolio?" --with-answers
```

Ожидание: IV достаточно портфолио, резюме необязательно. PDF page 24 / IV.
Цитата на английском, ответ на русском; цитата не должна быть переводом или выдумкой.

## 4. Слабый контекст

```powershell
python projects/week-5-task-4/main.py --question "Как приготовить борщ с говядиной?" --with-answers
```

Ожидание: `final_chunks: 0`, `ANSWER [unknown]`, «Не знаю» и просьба уточнить.
Источников/цитат нет: их нельзя выдумывать для отказа.
При необходимости показать принудительно высокий порог:

```powershell
python projects/week-5-task-4/main.py --threshold 1 --with-answers
```

## 5. Десять вопросов и контроль цитат

```powershell
python projects/week-5-task-4/main.py --evaluate --with-answers --output projects/week-5-task-4/data/evaluation-answers.json
```

Дождаться `SUMMARY`, `Saved`. Обычно 20 платных запросов, до 30 с повторными
генерациями после невалидных цитат или схемы. Для короткой записи можно
открыть результат заранее выполненного прогона, прямо назвав его сохранённым:

```powershell
$report = Get-Content -Raw -Encoding UTF8 projects/week-5-task-4/data/evaluation-answers.json | ConvertFrom-Json
$report.summary | ConvertTo-Json -Depth 4
```

Открыть `results.md`: ручное сравнение смысла десяти ответов с цитатами.
Показать проверки:

```powershell
python -m unittest discover projects/week-5-task-4 -v
```

Объяснить: тесты отклоняют выдуманную цитату и чужой chunk_id. Проверка
дословности автоматическая, проверка логической поддержки — ручная.
