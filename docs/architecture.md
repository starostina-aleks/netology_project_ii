
```mermaid
graph TD
    USER["Клиент<br/>Telegram / Web"] --> GW["<b>API Gateway</b><br/>nginx<br/>auth, rate limit"]
    GW --> SVC["<b>Service</b><br/>FastAPI<br/>Bulkhead: семафоры на endpoints"]
    SVC --> CACHE["<b>Cache-Aside</b><br/>Redis, TTL 1h<br/>key: hash(model+msgs+temp)"]
    CACHE -.->|"miss"| LLM["<b>LLM слой</b><br/>Fallback chain:<br/>OpenAI → Anthropic → Ollama"]
    CACHE -.->|"hit"| SVC
    LLM --> EXT["Провайдеры"]
    SVC --> DATA["<b>Data Layer</b><br/>Postgres: history, metrics<br/>Redis: sessions, RL counter"]
    SVC --> RAG["<b>RAG</b><br/>Embedding Model<br/>Vector DB"]
    RAG -.-> LLM


    style USER fill:#eef2ff,stroke:#6366f1,stroke-width:2px
    style GW fill:#ecfdf5,stroke:#10b981,stroke-width:2px
    style SVC fill:#eef2ff,stroke:#6366f1,stroke-width:2px
    style CACHE fill:#fefce8,stroke:#f59e0b,stroke-width:2px
    style LLM fill:#ecfdf5,stroke:#10b981,stroke-width:2px
    style DATA fill:#fefce8,stroke:#f59e0b,stroke-width:2px
    style RAG fill:#fefce8,stroke:#f59e0b,stroke-width:2px
    style EXT fill:#fefce8,stroke:#f59e0b,stroke-width:2px
```

## ADR-001: Выбор паттерна взаимодействия
**Status:** Accepted (2026-04-XX)
**Context.** Проект — чат-бот в Telegram для технической поддержки. Ожидаемая
нагрузка — 100 сообщений/мин в пике, средний ответ — 300–500 токенов
(2–6 секунд генерации), бюджет $30/мес.
**Decision.** Выбран **Streaming через SSE**. Telegram-бот редактирует
сообщение по мере прихода токенов (паттерн edit-message).
**Consequences.**
- Плюсы: TTFT 200–600 мс — пользователь сразу видит реакцию.
- Минусы: на nginx нужно отключить proxy_buffering; FastAPI держит
открытое соединение 5–10 сек на каждого пользователя (но asyncio это держит).
**Alternatives.**
- Request-Response — отвергнут, 5–10 секунд молчания в чате — плохой UX.
- Queue-based — отвергнут, для интерактивного чата избыточно: добавляет polling
и убивает «печать в реальном времени».
## ADR-002: Стратегия fault tolerance
**Decision.** Primary — OpenAI gpt-5-mini (баланс цена/качество).
Fallback — Anthropic claude-sonnet-4-6. Tertiary — Ollama qwen3:32b
(локально, на случай полного отказа облаков).
Circuit Breaker — `aiobreaker`, fail_max=5, timeout=60s, **по одному на
провайдера**. Cache-Aside в Redis, TTL 1 час, ключ —
`sha256(model + messages + temperature)`.
**Consequences.** Доступность сервиса гарантируется даже при одновременном
падении OpenAI + Anthropic (Ollama держит UX «работаем в ограниченном режиме»).
Стоимость: дополнительные $5/мес за минимальный Anthropic-трафик и
self-hosted Ollama на VPS.
