## 1) Сохранение состояний
В проекте реализовано динамическое переключение бэкендов сохранения состояний в зависимости от среды выполнения:

* **`AsyncSqliteSaver` (для тестов и локальной разработки):** обеспечивает быстрый запуск приложения без развертывания внешней инфраструктуры, сохраняя сессии в локальный файл.
* **`AsyncPostgresSaver` (для продакшена):** гарантирует отказоустойчивость, масштабируемость и единый централизованный источник правды для историй диалогов при горизонтальном масштабировании приложения.

Выбор бэкенда происходит прозрачно при инициализации графа через переменную окружения `settings.agent_checkpointer`.

## 2) Развертывание и верификация базы данных PostgreSQL для хранения состояний
###  Конфигурация Postgres в docker-compose
```bash
   postgres:
    image: postgres:16
    container_name: llm-postgres
    restart: unless-stopped
    environment:
      POSTGRES_DB: chat
      POSTGRES_USER: chat
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-chat}
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    healthcheck:
      test: [ "CMD-SHELL", "pg_isready -U chat" ]
      interval: 10s
      timeout: 3s
      retries: 5' 
```
### Подключение к Postgres (async-драйвер asyncpg)
DATABASE_URL=postgresql+asyncpg://chat:chat@localhost:5432/chat
### Проверка таблиц после checkpointer.setup()
```bash
docker exec -it llm-postgres psql -U chat
psql (16.15 (Debian 16.15-1.pgdg13+2))
Type "help" for help.
chat-# \dt
               List of relations
 Schema |         Name          | Type  | Owner 
--------+-----------------------+-------+-------
 public | alembic_version       | table | chat
 public | chat_messages         | table | chat
 public | chats                 | table | chat
 public | checkpoint_blobs      | table | chat
 public | checkpoint_migrations | table | chat
 public | checkpoint_writes     | table | chat
 public | checkpoints           | table | chat
 public | rag_queries           | table | chat
(8 rows)
```

## 3) Механизм контроля опасных операций (Human-in-the-Loop)

В качестве опасного инструмента выбран **`add_custom_synonym`**. 

Обогащает лингвистическую базу корпоративного поискового движка.
Связывает аббревиатуры, внутренний сленг или сокращения с их полными и альтернативными названиями.
* **`abbreviation`**: Исходное сокращение, аббревиатура или ключевое слово (например, 'ВВС').
* **`synonyms`**: Список альтернативных названий, сленга, расшифровок или близких по смыслу терминов (например, ['Военно-воздушные силы']).

До срабатывания `interrupt` условный переход `route_after_model` перенаправляет поток в узел `prepare_synonyms`, где из аргументов вызова LLM формируется безопасный черновик (`draft`) с сохранением обязательного `tool_call_id`. 

После `interrupt` и получения ответа пользователя (`Command(resume)`): в узле `approve_and_add` либо выполняется транзакция через `service.add_synonym` (возвращающая статус операции: успешно добавлено, обновлено или ошибка), либо фиксируется отмена действия, после чего генерируется корректный `ToolMessage` для закрытия сессии OpenAI API и предотвращения ошибок валидации контекста.

## Mermaid-схема  графа

```mermaid
---
config:
  flowchart:
    curve: linear
---
graph TD;
	__start__([<p>__start__</p>]):::first
	call_model(call_model)
	execute_tool(execute_tool)
	prepare_synonyms(prepare_synonyms)
	approve_and_add(approve_and_add)
	force_finish(force_finish)
	__end__([<p>__end__</p>]):::last
	__start__ --> call_model;
	approve_and_add --> call_model;
	call_model -.-> execute_tool;
	call_model -.-> force_finish;
	call_model -.-> prepare_synonyms;
	execute_tool --> call_model;
	prepare_synonyms --> approve_and_add;
	force_finish --> __end__;
	classDef default fill:#f2f0ff,line-height:1.2
	classDef first fill-opacity:0
	classDef last fill:#bfb6fc
```

## 4) Лог выполнения 

```bash
✅ СТАТУС: Граф СВОБОДЕН (Выполнен или ожидает новый HumanMessage)

[node ['call_model']
ChatCompletion(id='gen-1791539666-fpA4BSt23O6WEHZnjIV4', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='ПЭЖ (пост энергетики и живучести) — это специализированное помещение на корабле, где размещаются командные пункты и осуществляется управление подчиненными. В ПЭЖ могут размещаться командные пункты, такие как главный командный пункт (ГКП) или центральный командный пункт (ЦКП) на надводных кораблях [1-Корабельный устав ВМФ.md].', refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=None, reasoning=None), native_finish_reason='stop')], created=1791539666, model='openai/gpt-4o-mini', object='chat.completion', moderation=None, service_tier='default', system_fingerprint='fp_3ee3a780c6', usage=CompletionUsage(completion_tokens=302, prompt_tokens=19860, total_tokens=20162, completion_tokens_details=None, prompt_tokens_details=None))
[node ['execute_tool']

[node ['call_model']

[node ['prepare_synonyms']

[node ['__interrupt__']
```

```bash
️  СТАТУС: Граф ПРИОСТАНОВЛЕН (Interrupt)
📍 Ожидает на узле (node): ['approve_and_add']
💬 Причина прерывания / Данные: (Interrupt(value={'preview': {'abbreviation': 'ПЭЖ', 'synonyms': ['пост энергетики и живучести', 'специализированное помещение на корабле, где размещаются командные пункты', 'главный командный пункт (ГКП)', 'центральный командный пункт (ЦКП)'], 'tool_call_id': 'call_Hml7CHqNw3a7nUZ6oKJQmp00'}, 'type': 'approve_add_synonym'}, id='ab001f6fcd881cb6a24abf666285b3f1', response_schema=None),)
CONTENT: Успешно. Для аббревиатуры 'пэж' добавлено 3 официальных терминов.
Успешно. Для аббревиатуры 'пэж' добавлено 3 официальных терминов.
[node ['approve_and_add']
Я снова нашел расшифровку аббревиатуры ПЭЖ: это "пост энергетики и живучести", специализированное помещение на корабле, где размещаются командные пункты, такие как главный командный пункт (ГКП) или центральный командный пункт (ЦКП). Я добавил эту информацию в базу данных.
[node ['call_model']

[node ['force_finish']
```
### 5) Time travel:

1) INTERRUPT payload: {'preview': {'abbreviation': 'СУБД', 'synonyms': ['система управления базами данных'], 'tool_call_id': 'call_V2aMpmEnK7OjxrP4EZO33F8a'}, 'type': 'approve_add_synonym'}
2) история чек-пойнтов (checkpoint_id / next / ключи state):
   1f1c3c61-9b6c-6d8b-8002-3574a769fa9f  next=('approve_and_add',)
   1f1c3c61-9b6a-6676-8001-3bbff515d899  next=('prepare_synonyms',)
   1f1c3c61-8e07-6a2a-8000-9519574d5f8a  next=('call_model',)
   1f1c3c61-8e00-64fa-bfff-d7d14a0cd9c5  next=('__start__',)
3) чтение прошлого чек-пойнта: saved=False, draft_готов=True, next=('approve_and_add',)
4) две ветки: отказ → is_synonym_saved=False, одобрение → sent=False, отправок=0
Итог: один и тот же вход дал две ветки — отказ (sent=False) и одобрение (sent=True).

### 6) Поток событий узлов и токенов POST /agent/stream

* до `interrupt`

```bash
data: {"type": "update", "nodes": ["call_model"]}

data: {"type": "token", "text": "ChatCompletion(id='gen-1791537184-ctTcGZQ7RkmT60aObLX3', choices=[Choice(finish_reason='stop', index=0, logprobs=None, message=ChatCompletionMessage(content='ПЭЖ (пост энергетики и живучести) — это специализированное помещение на корабле, где размещаются командные пункты и осуществляется управление подчиненными. В ПЭЖ могут находиться командные пункты, такие как главный командный пункт (ГКП) или центральный командный пункт (ЦКП) [1-Корабельный устав ВМФ.md].', refusal=None, role='assistant', annotations=None, audio=None, function_call=None, tool_calls=None, reasoning=None), native_finish_reason='stop')], created=1791537184, model='openai/gpt-4o-mini', object='chat.completion', moderation=None, service_tier='default', system_fingerprint='fp_3ee3a780c6', usage=CompletionUsage(completion_tokens=279, prompt_tokens=19860, total_tokens=20139, completion_tokens_details=None, prompt_tokens_details=None))"}

data: {"type": "update", "nodes": ["execute_tool"]}

data: {"type": "update", "nodes": ["call_model"]}

data: {"type": "update", "nodes": ["prepare_synonyms"]}

data: {"type": "interrupt", "payload": {"preview": {"abbreviation": "ПЭЖ", "synonyms": ["пост энергетики и живучести"], "tool_call_id": "call_o01IctuSkltPmqjcoH96396k"}, "type": "approve_add_synonym"}}

data: {"type": "done"}
```

## Поток событий узлов и токенов POST /agent/resume 
* resume = False, после `interrupt`

```bash
{
  "status": "done",
  "thread_id": "091026_test_1",
  "answer": "Я нашел расшифровку ПЭЖ: \"пост энергетики и живучести\". Однако добавление в базу данных было отменено. Если вы хотите, я могу повторить попытку добавить эту информацию.",
  "tool_results": [
    {
      "name": "add_custom_synonym",
      "args": {
        "abbreviation": "ПЭЖ",
        "synonyms": [
          "пост энергетики и живучести"
        ],
        "tool_call_id": "call_o01IctuSkltPmqjcoH96396k"
      },
      "result": "Действие отменено пользователем"
    }
  ],
  "interrupt": null
}
```