# Неделя 1, задание 2: управление форматом ответа

CLI-приложение сравнивает один запрос к DeepSeek API без ограничений и с контролем структуры ответа.

## Что проверяется

- явный JSON-формат;
- фиксированный набор полей;
- питч длиной не более 30 слов;
- `max_tokens=200`;
- завершение по `stop=["<END>"]`;
- сохранение схемы в 20 одинаковых запросах.

Значения и формулировки могут различаться. Стабильной должна оставаться структура.

## Требования

- Python 3.11+
- API-ключ DeepSeek

Сторонние библиотеки не требуются.

## Настройка

Создайте `.env` в корне репозитория:

```env
DEEPSEEK_API_KEY=your_api_key
```

Файл `.env` исключён из Git.

## Запуск

```powershell
python projects/week-1-task-2/main.py
```

Доступны три режима:

```text
1 = один запрос без контроля
2 = 20 запросов с контролем и проверкой схемы
3 = сравнение обоих режимов
```

В режиме сравнения сначала введите данные для обычного запроса, затем повторите их для контролируемого:

```text
Mode [1 = without controls, 2 = with controls, 3 = compare]: 3

WITHOUT CONTROLS
Name: Astin Ray, VAVA - TAKIPARIO
Description: agressive phonk with female vocal

WITH CONTROLS
Name: Astin Ray, VAVA - TAKIPARIO
Description: agressive phonk with female vocal
```

Разные входные данные остановят сравнение.

## Контролируемая схема

```json
{
  "track": "Astin Ray, VAVA - TAKIPARIO",
  "pitch": "English pitch with 30 words or fewer",
  "content_uses": ["Use 1", "Use 2", "Use 3"]
}
```

Приложение использует `response_format={"type": "json_object"}`, разбирает каждый ответ через `json.loads()` и проверяет ключи, типы, количество элементов и длину питча.

Успешный итог:

```text
SCHEMA RESULT: 20/20 responses matched
```

## Тест

```powershell
python -m unittest discover projects/week-1-task-2
```
