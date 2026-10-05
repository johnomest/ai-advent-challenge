# День 21 — индексация базы знаний GOOST

Подробный [сценарий записи и чеклист](VIDEO-SCENARIO.md).

Проект готовит локальные RAG-индексы из Markdown-документации `goost-tools`. Содержимое файлов не отправляется в облако: embeddings строит локальный Ollama.

## Что изучаем

- подготовку документов для RAG;
- fixed-size и structural chunking;
- локальные multilingual embeddings;
- сохранение индекса и метаданных;
- влияние стратегии чанкинга на результат.

## Данные

По умолчанию читается соседний репозиторий:

```text
D:\Work\Projects\goost-tools\documentation
```

Индексируются только файлы `*.md`. Telegram JSON, `.env`, secrets, код и логи не читаются. Для каждого чанка сохраняются:

- `source`;
- `title`;
- `section`;
- `chunk_id`;
- `strategy`;
- текст и embedding.

## Подготовка Ollama

Установить Ollama, затем загрузить компактную multilingual-модель:

```powershell
ollama pull embeddinggemma
```

`embeddinggemma` занимает около 622 MB и поддерживает более 100 языков.

## Запуск

Из корня учебного репозитория:

```powershell
python projects/week-5-task-1/main.py
```

Результат:

```text
projects/week-5-task-1/data/index-fixed.json
projects/week-5-task-1/data/index-structure.json
```

Фактический результат на документации `goost-tools`:

```text
fixed      chunks= 509 sources= 43 avg_words=172
structure  chunks= 895 sources= 43 avg_words= 89
embedding dimensions=768
```

Папка `data` исключена из Git: рабочая документация и embeddings не публикуются.

Другой источник можно передать явно:

```powershell
python projects/week-5-task-1/main.py --source D:\path\to\markdown
```

## Проверка

```powershell
python -m unittest discover projects/week-5-task-1 -v
```

## Что показать на видео

1. Показать источник Markdown и ограничения безопасности.
2. Показать две функции: `fixed_chunks` и `structured_chunks`.
3. Запустить индексатор.
4. Сравнить число чанков и средний размер для двух стратегий.
5. Показать два созданных индекс-файла и метаданные одного чанка.
6. Подвести итог: fixed-size проще, structural chunking лучше сохраняет разделы документа.

## Вывод

Одна база знаний превращена в два локальных векторных индекса. Fixed-size стратегия даёт равномерные фрагменты, но может разрезать смысловые блоки. Structural chunking сохраняет заголовки и происхождение информации, поэтому удобнее для ответов со ссылками на источники.

## Источники

- [Ollama Generate embeddings API](https://docs.ollama.com/api/embed)
- [EmbeddingGemma in Ollama](https://ollama.com/library/embeddinggemma)
