## Что такое **LiteLLM**

**LiteLLM** – это лёгкая обёртка (wrapper) над различными LLM‑провайдерами (OpenAI, Anthropic, Azure, Cohere, Vertex AI и т.д.).  
Она позволяет:

| Возможность | Что делает LiteLLM |
|-------------|-------------------|
| **Unified API** | Один и тот же Python‑интерфейс `completion/create`, `chat/completion/create`, `embedding/create` и др. независимо от того, к какому провайдеру вы обращаетесь. |
| **Мульти‑провайдерный роутинг** | Вы задаёте «primary» и «fallback» (или любые другие) провайдеры, а LiteLLM сам переключается на запасной, если основной отказывает. |
| **Rate‑limit & caching** | Ограничивает запросы, кэширует ответы, поддерживает токен‑лимиты. |
| **Теле‑метрика и логирование** | Через `litellm.logging` можно выводить детальные логи в файл, stdout, Sentry, LangChain‑compatible tracing и т.п. |
| **Конфигурация через YAML/JSON** | Параметры (API‑ключи, endpoint‑ы, роутинг, fallback‑правила) удобно хранить в `config.yaml` и передавать в `LiteLLM` при старте. |

---

## Как подключить **LiteLLM** к локальному прокси OpenAI

```python
from litellm import LiteLLM, TextCompletionResponse

# Пример клиента, использующего локальный прокси (например, Ollama, vLLM, локальный сервер OpenAI‑compatible)
client = LiteLLM(
    api_key="dummy",                     # ключ не нужен, но обязателен в сигнатуре
    base_url="http://localhost:4000/v1" # endpoint вашего прокси
)

# Простой запрос
resp: TextCompletionResponse = client.completion(
    model="gpt-3.5-turbo",               # любой модельный идентификатор, поддерживаемый прокси
    messages=[{"role": "user", "content": "Привет!"}]
)

print(resp.choices[0].message.content)
```

> **Важно:** в `base_url` указывается полный путь до `/v1` (или другого пути, который ваш прокси использует для совместимости с OpenAI). Если ваш прокси работает без `/v1`, просто укажите `http://localhost:4000`.

---

## Где и как настроить вывод логов в `config.yaml`

### 1. Минимальная структура `config.yaml`

```yaml
# config.yaml
litellm:
  # --- Параметры глобального роутинга
  routing:
    # primary – провайдер, который будет использоваться по‑умолчанию
    primary:
      model: "gpt-3.5-turbo"
      provider: "openai"
      api_key: "sk-PRIMARY-KEY"
      base_url: "https://api.openai.com/v1"

    # fallback – запасной провайдер, включается при любой ошибке primary
    fallback:
      model: "claude-2.0"
      provider: "anthropic"
      api_key: "sk-FALLBACK-KEY"
      base_url: "https://api.anthropic.com"

  # --- Логирование
  logging:
    # Вариант 1 – простой вывод в консоль
    console:
      enabled: true
      level: "INFO"                # DEBUG, INFO, WARNING, ERROR
    # Вариант 2 – запись в файл
    file:
      enabled: true
      level: "DEBUG"
      path: "./logs/litellm.log"
      rotation: "10 MB"           # или "daily"
    # Вариант 3 – отправка в Sentry (опционально)
    sentry:
      enabled: false
      dsn: ""                      # ваш DSN
```

### 2. Как подключить этот файл к `LiteLLM`

```python
import litellm
from litellm import LiteLLM
from pathlib import Path
import yaml

# 1️⃣ Загрузить yaml
CONFIG_PATH = Path(__file__).parent / "config.yaml"
with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

# 2️⃣ Инициализировать клиент с роутингом и логированием
client = LiteLLM(
    # ---------- роутинг ----------
    model=cfg["litellm"]["routing"]["primary"]["model"],
    provider=cfg["litellm"]["routing"]["primary"]["provider"],
    api_key=cfg["litellm"]["routing"]["primary"]["api_key"],
    base_url=cfg["litellm"]["routing"]["primary"]["base_url"],

    # ---------- fallback ----------
    fallback_model=cfg["litellm"]["routing"]["fallback"]["model"],
    fallback_provider=cfg["litellm"]["routing"]["fallback"]["provider"],
    fallback_api_key=cfg["litellm"]["routing"]["fallback"]["api_key"],
    fallback_base_url=cfg["litellm"]["routing"]["fallback"]["base_url"],

    # ---------- логирование ----------
    # Параметры logger'а автоматически читаются из `litellm.logging`
    # но можно задать их явно:
    logger_kwargs={
        "console_enabled": cfg["litellm"]["logging"]["console"]["enabled"],
        "console_level": cfg["litellm"]["logging"]["console"]["level"],
        "file_enabled": cfg["litellm"]["logging"]["file"]["enabled"],
        "file_level": cfg["litellm"]["logging"]["file"]["level"],
        "file_path": cfg["litellm"]["logging"]["file"]["path"],
        "file_rotation": cfg["litellm"]["logging"]["file"]["rotation"],
    },
)

# Теперь любые вызовы будут автоматически логироваться.
```

> **Почему `fallback_*` передаются явно?**  
> В текущей версии `litellm` (по состоянию на 2024‑2025) в `LiteLLM` нет единого параметра `config`‑объекта. Поэтому fallback‑параметры передаются отдельными аргументами (`fallback_model`, `fallback_provider` и т.д.). Если вы используете более новую ветку, где поддерживается `client = LiteLLM(**cfg["litellm"]["routing"])`, просто распакуйте словарь.

### 3. Как проверить переключение провайдера

```python
def ask(prompt: str):
    try:
        # Ставим небольшую таймаут‑запрос, чтобы имитировать ошибку primary
        resp = client.completion(
            model=cfg["litellm"]["routing"]["primary"]["model"],
            messages=[{"role": "user", "content": prompt}],
            timeout=2  # секунды
        )
        print("✅ Primary response:", resp.choices[0].message.content)
    except Exception as e:
        print("⚠️ Primary провайдер упал, переключаемся на fallback...")
        # Переиспользуем тот же клиент, но у него уже настроен fallback
        resp = client.completion(
            model=cfg["litellm"]["routing"]["fallback"]["model"],
            messages=[{"role": "user", "content": prompt}]
        )
        print("✅ Fallback response:", resp.choices[0].message.content)

# Пример: искусственно отключаем локальный сервер
ask("Расскажи анекдот про программиста.")
```

**Что будет в логах?**

* В **консоль** (если `console.enabled: true`) увидите строки вроде:

```
2024-06-14 12:34:56,789 | INFO | litellm.routing | Sending request to primary provider (openai) – model=gpt-3.5-turbo
2024-06-14 12:34:58,001 | ERROR | litellm.routing | Primary provider failed: ConnectTimeoutError
2024-06-14 12:34:58,002 | INFO | litellm.routing | Switching to fallback provider (anthropic) – model=claude-2.0
2024-06-14 12:34:58,345 | INFO | litellm.routing | Fallback response received (tokens=45)
```

* В **файловый лог** (`./logs/litellm.log`) будет полная трассировка с `DEBUG`‑уровнем, включая заголовки запросов, токены, время отклика и стек‑трейсы исключений.

Эти сообщения генерируются внутренним `Logger`‑ом `litellm.logging`. Если вы хотите изменить формат (JSON, обычный текст, добавить `request_id`), достаточно переопределить `logger_kwargs["log_formatter"]` в момент создания клиента.

---

## Краткое напоминание о типичных ошибках

| Ошибка | Причина | Как отладить (через логи) |
|--------|----------|---------------------------|
| `ConnectTimeoutError` | primary‑endpoint недоступен | В логе появится `ERROR` с `timeout`‑сообщением. |
| `OpenAIError: Rate limit exceeded` | превысили лимит запросов | В логе будет `WARN` с кодом `429`. |
| `AuthenticationError` | неверный API‑key | `ERROR` + сообщение `Invalid Authentication`. |
| `InvalidRequestError` | модель не поддерживается у провайдера | `ERROR` + `model not found`. |
| `Fallback not configured` | в `config.yaml` нет раздела `fallback` | При старте появится `WARNING: fallback configuration missing`. |

---

## Полезные ссылки

| Что | Ссылка |
|-----|--------|
| Официальный репозиторий LiteLLM | <https://github.com/BerriAI/litellm> |
| Документация по роутингу и fallback | <https://docs.litellm.ai/docs/routing> |
| Пример `config.yaml` (advanced) | <https://github.com/BerriAI/litellm/blob/main/examples/config.yaml> |
| Логирование и кастомные хендлеры | <https://docs.litellm.ai/docs/logging> |
| Интеграция с Sentry | <https://docs.litellm.ai/docs/sentry> |

---

### Итоги

1. **`config.yaml`** – здесь задаются как провайдеры (`primary`, `fallback`), так и параметры логирования (`console`, `file`, `sentry`).  
2. При инициализации `LiteLLM` из Python‑кода вы **разбираете** yaml и передаёте параметры в конструктор, включив `logger_kwargs`.  
3. Логи (консоль + файл) покажут, когда происходит переключение: сначала запись о запросе к `primary`, затем `ERROR`‑сообщение, после чего `INFO`‑запись о переходе к `fallback`.  
4. Благодаря `DEBUG`‑уровню в файловом логе вы увидите полные запросы‑ответы, тайминги и стек‑трейсы, что позволяет быстро диагностировать, *почему* primary упал и насколько быстро сработал fallback.

Если понадобится добавить третий уровень (secondary) или кастомный «policy»‑handler, просто расширьте секцию `routing` в `config.yaml` и соответствующим образом модифицируйте `logger_kwargs`. Happy LLM‑routing!


**Litellm** – это лёгкая обёртка над различными LLM‑апи (OpenAI, Anthropic, Cohere, Azure, HuggingFace и т.д.), которая упрощает работу с моделями,统一​‑т единый интерфейс и добавляет полезные возможности:  
- автоматический роутинг запросов между несколькими провайдерами;  
- поддержка **prompt caching**, **batch‑запросов**, **stream‑ответов**;  
- встроенный мониторинг, логирование и **локальный кэш**;  
- гибкая настройка через `config.yaml` (или переменные окружения).  

Ниже – пошаговое руководство, как включить и сконфигурировать локальный кэш для Litellm с помощью файла `config.yaml`.

---

## 1️⃣ Установка Litellm

```bash
# Виртуальное окружение (рекомендовано)
python -m venv .venv
source .venv/bin/activate   # .venv\Scripts\activate на Windows

pip install litellm
```

> **Важно:** Для кэша требуется Python ≥ 3.9 и `redis` (или `sqlite`‑based fallback). Если планируете использовать Redis, установите клиент:

```bash
pip install "litellm[redis]"
```

---

## 2️⃣ Что такое “локальный кэш” в Litellm?

Litellm может кэшировать ответы моделей (по запросу или по **prompt‑hash**), чтобы повторно использовать их при одинаковых входных данных. Это:

- **Сокращает расходы** (не отправляем одинаковый запрос к платным API);
- **Ускоряет** отклик (чтение из кэша быстрее, чем сетевой запрос);
- **Обеспечивает детерминированность** в тестах и прототипах.

Кэш может храниться:
| Тип          | Где хранится            | Плюсы/минусы |
|--------------|------------------------|--------------|
| **In‑memory**| Оперативная память процесса | Мгновенный доступ, но исчезает при рестарте |
| **SQLite**   | Файл `cache.db` в текущей папке | Не требует отдельного сервера, простой, подходит для небольших проектов |
| **Redis**    | Отдельный Redis‑сервер (локальный или в облаке) | Высокая производительность, поддержка TTL, распределённый кэш |

В примерах ниже будем использовать **SQLite** (самый простой старт), а в конце покажем, как переключиться на Redis.

---

## 3️⃣ Структура `config.yaml`

Litellm читает параметры из `config.yaml`, находящегося в корне проекта (или по пути, указанному в переменной `LITELLM_CONFIG_PATH`). Основные секции:

```yaml
# config.yaml
litellm:
  # Список провайдеров и их ключей
  model_list:
    - model_name: "gpt-3.5-turbo"
      litellm_params:
        model: "openai/gpt-3.5-turbo"
        api_key: "sk-..."
    - model_name: "claude-2"
      litellm_params:
        model: "anthropic/claude-2"
        api_key: "sk-ant-..."

  # Общие настройки
  default_team: "my_team"
  routing_strategy: "least_budget"   # optional
  max_parallel_requests: 5

  # ------------------ КЭШ ------------------
  cache:
    # тип хранилища: "sqlite", "redis", "memory"
    type: "sqlite"

    # Параметры для конкретного типа
    sqlite:
      # Путь к файлу БД (относительно корня проекта)
      db_path: "./cache.db"
      # Как часто (в сек.) будет очищаться просроченный кэш (0 = отключить)
      ttl_seconds: 0

    redis:
      host: "localhost"
      port: 6379
      password: null
      # Время жизни кэш‑записей (seconds). 0 = без истечения.
      ttl_seconds: 86400

    # Общие опции
    enabled: true               # вкл/выкл кэш полностью
    max_cache_size: 1000000     # максимум записей (по‑умолчанию 1 млн)
    # Если включён, будет кэшировать **полный запрос** (prompt + параметры)
    cache_by: "hash"            # "hash" (по запросу), "prompt" (только prompt), "none"

  # Логи
  logging:
    level: "INFO"
    file: "./litellm.log"
```

### Пояснения к ключевым полям

| Параметр | Что делает |
|----------|------------|
| `cache.enabled` | Отключить/включить кэширование полностью. |
| `cache.type` | Выбирает backend (`sqlite`, `redis`, `memory`). |
| `sqlite.db_path` | Путь к SQLite‑файлу. Если файл не существует, Litellm создаст его автоматически. |
| `redis.host` / `port` / `password` | Параметры подключения к Redis. |
| `ttl_seconds` | Время жизни записи (Time‑to‑Live). `0` — бесконечно. |
| `cache_by` | Определяет, как рассчитывать хеш: `hash` — учитывает **весь запрос** (prompt + параметры), `prompt` — только текст prompt (полезно, если параметры меняются, но смысл тот же). |
| `max_cache_size` | Ограничение количества записей; при превышении старые удаляются по LRU. |

---

## 4️⃣ Пример использования Litellm с кэшем

```python
import litellm

# Если переменной окружения LITELLM_CONFIG_PATH нет, Litellm возьмёт config.yaml из текущей папки
# litellm.initialize() вызывается автоматически при первом вызове клиента

def ask_gpt(prompt: str):
    response = litellm.completion(
        model="gpt-3.5-turbo",   # имя из model_list
        messages=[{"role": "user", "content": prompt}],
        # Если хотите явно переопределить кэш‑поведение:
        # cache={"enabled": True, "ttl_seconds": 3600}
    )
    return response["choices"][0]["message"]["content"]

# Тестируем кэш
if __name__ == "__main__":
    print(ask_gpt("Расскажи шутку про программистов."))
    # При втором вызове тот же prompt будет обслужен из кэша (лог покажет "Cache hit")
    print(ask_gpt("Расскажи шутку про программистов."))
```

Запуск покажет в консоли (или в `litellm.log`) сообщения вроде:

```
2024-06-14 12:03:21,123 INFO litellm.cache Cache miss for hash abcdef1234...
2024-06-14 12:03:21,456 INFO litellm.cache Cache stored for hash abcdef1234
2024-06-14 12:03:23,001 INFO litellm.cache Cache hit for hash abcdef1234
```

---

## 5️⃣ Как переключить кэш с SQLite на Redis

1. **Установите Redis** (если ещё не установлен). На локальном Linux/macOS:

```bash
docker run -d --name redis -p 6379:6379 redis:7-alpine
```

2. **Обновите `config.yaml`**:

```yaml
cache:
  type: "redis"
  enabled: true
  redis:
    host: "localhost"
    port: 6379
    password: null
    ttl_seconds: 86400   # 1 день
```

3. **Перезапустите процесс** (чтобы Litellm перечитал конфиг). Всё — кэш будет храниться в Redis, что удобно для многопроцессных/кластерных сценариев.

> **Совет:** При работе в продакшене задайте `ttl_seconds` ≈ `86400`–`604800` (1‑7 дней), чтобы кэш не рос бесконечно, но сохранял часто используемые запросы.

---

## 6️⃣ Расширенные возможности кэша

| Функция | Как включить |
|---------|--------------|
| **Cache invalidation by tag** | В запросе передайте `metadata={"cache_tags": ["user_123"]}` и позже `litellm.clear_cache_by_tag("user_123")`. |
| **Prefill cache** | Можно предварительно заполнить кэш, вызвав `litellm.cache.insert(hash, response, ttl_seconds=…)`. |
| **Custom serializer** | Для сложных объектов (например, с бинарными изображениями) укажите `cache.serializer: "json"` или свой класс, реализующий `dumps/loads`. |
| **Bulk eviction** | `litellm.cache.evict(limit=1000)` удалит `limit` самых старых записей. |

---

## 7️⃣ Полезные команды для диагностики

```bash
# Показать текущий статус кэша (SQLite)
sqlite3 cache.db "SELECT COUNT(*) FROM cache;"

# Если используете Redis
redis-cli -p 6379 DBSIZE          # количество записей
redis-cli -p 6379 INFO | grep hits   # hit/miss статистика
```

Litellm также экспортирует метрики в Prometheus (если включить `observability` в конфиге), что позволяет строить графики `cache_hits_total`, `cache_misses_total` и т.д.

---

## 8️⃣ Часто задаваемые вопросы (FAQ)

| Вопрос | Ответ |
|--------|-------|
| **Кешируется ли только `completion`, или тоже `embedding`?** | По умолчанию кэшируется любой вызов, где `model` поддерживает кэширование (completion, chat, embeddings). Для embeddings рекомендуется использовать отдельный префикс `embed_` в `model_name`, чтобы не перемешивать ответы. |
| **Можно ли отключить кэш для конкретного запроса?** | Да: `litellm.completion(..., cache={"enabled": False})`. |
| **Что делать, если кэш занимает слишком много места?** | Установите `max_cache_size` в `config.yaml` или явно вызывайте `litellm.cache.evict()` в планировщике. |
| **Кэш не работает – получаю только “Cache miss”.** | Проверьте, что `cache.enabled: true` и `type` совпадает с установленным клиентом (`pip install litellm[redis]` для Redis). Также убедитесь, что `model` указан точно так же, как в `model_list`. |
| **Можно ли использовать разные типы кэша для разных моделей?** | На данный момент кэш задаётся глобально, но вы можете создать два отдельных процесса/контейнера с разными `config.yaml` и роутировать запросы через `router`‑функцию Litellm. |

---

## 9️⃣ Быстрый чек‑лист для запуска

1. ✅ Создайте `config.yaml` (пример выше).  
2. ✅ Установите необходимые зависимости (`litellm`, `litellm[redis]` если нужен Redis).  
3. ✅ Запустите Redis (если выбран тип `redis`).  
4. ✅ Выполните первый запрос – в логах будет `Cache miss`.  
5. ✅ Выполните тот же запрос второй раз – увидите `Cache hit`.  
6. ✅ При необходимости настройте TTL, размер и тип кэша.  

---

## 🔚 Итоги

- **Litellm** упрощает работу с множеством LLM‑провайдеров.  
- Кеширование – один из ключевых плюсов, позволяющий экономить деньги и ускорять ответы.  
- Конфигурация полностью задаётся в `config.yaml`; достаточно изменить секцию `cache` и перезапустить процесс.  
- Для небольших проектов подойдет SQLite, а для продакшена – Redis (масштабируемый, поддерживает TTL и многопроцессный доступ).  

Если понадобится более детальная настройка (например, интеграция с FastAPI, Celery, или Prometheus‑мониторинг), дайте знать – подготовлю отдельный пример!
