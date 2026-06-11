flowchart LR
USER["Клиент<br/>Telegram / Web"] --> GW["<b>API Gateway</b><br/>nginx<br/>auth, rate li
GW --> SVC["<b>Service</b><br/>FastAPI<br/>Bulkhead: семафоры на endpoints"]
SVC --> CACHE["<b>Cache-Aside</b><br/>Redis, TTL 1h<br/>key: hash#40;model+msgs+temp#41;
CACHE -.->|"miss"| LLM["<b>LLM слой</b><br/>Fallback chain:<br/>OpenAI → Anthropic → Oll
CACHE -.->|"hit"| SVC
LLM --> EXT["Провайдеры"]
SVC --> DATA["<b>Data Layer</b><br/>Postgres: history, metrics<br/>Redis: sessions, RL c
style USER fill:#eef2ff,stroke:#6366f1,stroke-width:2px
style GW fill:#ecfdf5,stroke:#10b981,stroke-width:2px
style SVC fill:#eef2ff,stroke:#6366f1,stroke-width:2px
style CACHE fill:#fefce8,stroke:#f59e0b,stroke-width:2px
style LLM fill:#ecfdf5,stroke:#10b981,stroke-width:2px
style DATA fill:#fefce8,stroke:#f59e0b,stroke-width:2px
style EXT fill:#fefce8,stroke:#f59e0b,stroke-width:2px