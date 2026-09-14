# karpaty-bot

Telegram-интерфейс для персональной базы знаний `mozg`.

Бот — один из интерфейсов к Markdown-базе знаний (`raw/`, `templates/`, `wiki/`).
`AGENTS.md` и `templates/` — контракт, который приложение читает у самой Wiki,
но не хранит внутри себя.

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
# заполнить TELEGRAM_BOT_TOKEN, WIKI_ROOT, LLM_*
python -m app.main
```

Long polling, webhook не используется.

## Конфигурация

См. `.env.example`. При запуске приложение проверяет, что
`WIKI_ROOT` содержит ожидаемую структуру (`AGENTS.md`, `raw/sources/`,
`templates/`, `wiki/`, `wiki/areas/`). Если структура отсутствует,
запуск завершается с ошибкой — бот не создаёт Wiki с нуля.

## Команды

`/start` `/help` `/capture` `/ingest` `/ask` `/recent` `/status` `/cancel`

Обычное текстовое сообщение без команды считается новой мыслью (Capture).

## Тесты

```bash
pytest
```

Все тесты работают только с временной фиктивной Wiki (`tmp_path`).
Реальная `~/mozg` не используется.