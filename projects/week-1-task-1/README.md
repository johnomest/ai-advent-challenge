# Неделя 1, задание 1: генератор музыкальных питчей

Минимальное CLI-приложение на Python. Отправляет данные трека в DeepSeek API и выводит музыкальный питч на английском языке.

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

Из корня репозитория:

```powershell
python projects/week-1-task-1/main.py
```

Введите название трека первой строкой и краткое описание второй:

```text
Name: TAKIPARIO
Description: Phonk track by Astin Ray and VAVA with Brazilian street energy, heavy bass, springy rhythm, and vocal hooks
```

Программа отправит данные модели `deepseek-v4-flash` и выведет питч из трёх предложений.

## Параметры генерации

Параметры находятся в `main.py`:

```python
"thinking": {"type": "disabled"},
"temperature": 0.5,
"top_p": 1.0,
"max_tokens": 200,
```

- `temperature` управляет вариативностью ответа.
- `top_p` оставлен в нейтральном значении, пока регулируется `temperature`.
- `max_tokens` ограничивает длину ответа.
