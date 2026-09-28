import argparse
import json
import logging
import time

from openai import OpenAI
from app.tools.naive_tools import DISPATCH,TOOLS
from app.core.config import get_settings
import inspect
import asyncio
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler("agent.log", encoding="utf-8"), # Запись в файл
        logging.StreamHandler(sys.stdout)                  # Дублирование в консоль
    ]
)
logger = logging.getLogger(__name__)

settings = get_settings()
_RESULT_PREVIEW_LEN = 200

def _trace_entry(
    step: int,
    tool_name: str | None,
    tool_args: str | None,
    tool_result: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    duration_ms: float,
) -> dict:
    """Одна запись трассы — единый формат для шага с инструментом и без него."""
    preview = None if tool_result is None else str(tool_result)[:_RESULT_PREVIEW_LEN]
    return {
        "step": step,
        "tool_name": tool_name,
        "tool_args": tool_args,
        "tool_result": preview,
        "llm_input_tokens": input_tokens,
        "llm_output_tokens": output_tokens,
        "duration_ms": duration_ms,
    }

async def _dispatch(name: str, raw_args: str) -> str:
    """Вызывает инструмент из allowlist; любую проблему возвращает строкой модели."""
    if name not in DISPATCH:
        return f"Ошибка: инструмент '{name}' недоступен. Доступные: {sorted(DISPATCH)}"
    try:
        arguments = json.loads(raw_args) if raw_args else {}
    except json.JSONDecodeError as exc:
        return f"Ошибка: не удалось разобрать аргументы ({exc})"
    try:
        tool_func = DISPATCH[name]
        if inspect.iscoroutinefunction(tool_func):
            result = await tool_func(**arguments)
        else:
            result = tool_func(**arguments)
        return str(result)
    except Exception as exc:
        logger.exception("инструмент %s завершился ошибкой", name)
        return f"Ошибка инструмента: {exc}"




async def run_agent(
        task: str,
        max_steps: int = 6,
        model: str = settings.llm.default_model,
        client: OpenAI | None = None,
)->dict:
    client=client or OpenAI(
       api_key=settings.llm.openai_api_key.get_secret_value(),
       base_url=settings.llm.base_url,
    )
    logger.info("task = %s", task)
    messages: list = [{"role": "user", "content": task}]
    trace: list[dict] = []
    for step in range(max_steps):
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=1024,
            tools=TOOLS,
        )
        message = response.choices[0].message
        duration_ms = round((time.perf_counter() - started) * 1000,1)
        messages.append(message)

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else None
        output_tokens = usage.completion_tokens if usage else None

        if not message.tool_calls:
            trace.append(
                _trace_entry(
                    step, None, None,message.content, input_tokens, output_tokens, duration_ms
                )
            )
            logger.info("step = %d финальный ответ", step)
            return {"answer": message.content,"step": step+1, "trace": trace}

        for call in message.tool_calls:
            name = call.function.name
            raw_args = call.function.arguments
            result = await _dispatch(name, raw_args)
            trace.append(
                _trace_entry(
                    step, name, raw_args, result, input_tokens, output_tokens, duration_ms
                )
            )
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result })
            logger.info("step=%d инструмент = %s -> %s", step, name, result[:300])

    logger.warning("исчерпан лимит шагов max_step=%d", max_steps)
    return {"answer": None, "step": max_steps, "trace": trace, "error": "max_steps"}

async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Наивный агент на Chat Completions")
    parser.add_argument("task",help="Задача для агента")
    parser.add_argument("--max-steps", type=int, default=6, help="Лимит шагов (guardrail)")
    parser.add_argument("--model", default="gpt-4o-mini", help="Модель Chat Completions")
    parser.add_argument("--trace", default=True,action="store_true", help="Печатать пошаговую трассу")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = await run_agent(args.task, max_steps=args.max_steps, model=args.model)

    if result.get("error"):
        print(f"Остановка: {result['error']} (шагов: {result['step']})")
    else:
        print(result["answer"])

    if args.trace:
        print("\n--- trace ---")
        for entry in result["trace"]:
            print(json.dumps(entry, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    # Запускаем асинхронный main() через asyncio.run и передаем результат в SystemExit
    sys.exit(asyncio.run(main()))