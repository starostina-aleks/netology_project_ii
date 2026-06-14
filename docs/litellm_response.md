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
