import structlog

def setup_logging(level: str | int = "INFO") -> None:
    structlog.configure(
       processors=[

       structlog.contextvars.merge_contextvars,
       structlog.processors.add_log_level,
       structlog.processors.TimeStamper(fmt="iso", utc=True),
       structlog.processors.JSONRenderer(ensure_ascii=False),
       ],
      # Главный элемент фильтрации: он сам отсечет логи ниже log_level
      wrapper_class=structlog.make_filtering_bound_logger(level),
    )
