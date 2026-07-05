from functools import lru_cache
from pathlib import Path
from jinja2 import Template
from typing import Any, Sequence
from app.schemas.chat import Message

PROMPTS_DIR = Path(__file__).parent

@lru_cache(maxsize=8)
def render_system_prompt(version: str = "v1", **context) -> str:
     text = (PROMPTS_DIR / f"system_{version}.j2").read_text(encoding="utf-8")
     return Template(text).render(**context)

def build_chat_prompt(
        system_prompt: str,
        history: Sequence[Message],  # Принимаем список готовых Pydantic-моделей
        user_message: str
) -> list[Message]:

     messages: list[Message] = [
          Message(role="system", content=system_prompt)
     ]
     messages.extend(history)
     messages.append(
          Message(role="user", content=user_message)
     )
     return messages