import argparse
import json
import logging
import time
from dataclasses import dataclass

from openai import OpenAI
from app.tools.react_tools import DISPATCH,TOOLS
from app.core.config import get_settings
import inspect
import asyncio
import sys
from typing import Literal
from pydantic import BaseModel


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

client = OpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url
)

class CriticDecision(BaseModel):
    status: Literal["OK", "REVISE"]
    reason: str

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

@dataclass
class RunUsage:
    calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def add(self, usage) -> None:
        self.calls += 1
        if usage is None:
            return
        self.prompt_tokens     += usage.prompt_tokens or 0
        self.completion_tokens += usage.completion_tokens or 0
        self.total_tokens      += usage.total_tokens or 0

    def as_dict(self) -> dict[str, int]:
        return {
                "calls": self.calls,
                "prompt_tokens":     self.prompt_tokens,
                "completion_tokens": self.completion_tokens,
                "total_tokens":      self.total_tokens,
        }

def reflect(messages: list[dict],usage_total:RunUsage) -> CriticDecision:
    critic_system_prompt = (
        "Ты — независимый Критик (Supervisor). Твоя задача — проанализировать "
        "последний шаг Агента (вызов инструмента и полученный Observation) в контексте "
        "всей истории решения задачи. Проверь: логичны ли были аргументы, не перепутал ли "
        "агент данные (города, даты, ID), и не является ли ответ пустой ошибкой, которую "
        "нужно исправить. Сделай вывод, можно ли продолжать (OK) или нужен пересмотр (REVISE)."
    )
    critic_messages = [
        {"role": "system", "content": critic_system_prompt},
        *messages  # Передаем всю текущую историю (включая только что добавленный tool_message)
    ]

    try:
        # Используем beta.chat.completions.parse для валидации схемы
        critic_response = client.beta.chat.completions.parse(
            model="gpt-4o-mini",
            messages=critic_messages,
            response_format=CriticDecision,
            max_tokens=1024,
        )
        usage_total.add(critic_response.usage)
        critic_decision = critic_response.choices[0].message.parsed
    except Exception as e:

        logger.warning(f"react.critic_failed_or_invalid: {e}", exc_info=True)
        # В случае редкой сетевой ошибки или таймаута критика — не роняем агентский цикл
        return CriticDecision(
            status = "OK",
            reason ="Сбой критика, продолжаем",
        )

    return critic_decision



async def run_agent(
        task: str,
        model: str = settings.llm.default_model,
        max_iterations: int = 10,
        timeout_per_iteration_sec: float = 100.0,
        max_revisions: int = 2,
)->dict:

    logger.info("task = %s", task)
    system_prompt = (
        "Действовать как агент: самостоятельно выбирать инструменты и их порядок, "
        "при необходимости разбивая задачу на подзадачи (в каждой подзадаче ОДИН иструмент). "
        "На каждом шаге сначала одним предложением пояснять, что и зачем делается, "
        "затем вызывать ровно ОДИН инструмент и опираться на его результат. "
        "Как только данных достаточно — дать финальный ответ без вызова инструментов. "
        "Не выдумывать данные: использовать только то, что вернули инструменты; "
        "если доступными инструментами задачу решить нельзя — прямо сообщить об этом."
        "Алгоритм шага: 1. Напиши мысль (что делаем). 2. Вызови ОДИН инструмент. "
        "3. Дождись ответа (Observation). Повторяй цикл, пока не решишь задачу."
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": task},
    ]
    trace: list[dict] = []
    usage_total = RunUsage()
    revisions_used = 0
    for step in range(max_iterations):
        t0 = time.monotonic()
        started = time.perf_counter()
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=1024,
            tools=TOOLS,
            tool_choice= {
                "type": "function",
                "function": {"name": "search_knowledge_base"}
            } if step == 0 else "auto",
            parallel_tool_calls = False
        )
        message = response.choices[0].message
        duration_ms = round((time.perf_counter() - started) * 1000,1)
        messages.append(message)

        usage = response.usage

        usage_total.add(usage)

        if not message.tool_calls:
            trace.append(
                _trace_entry(
                    step, None, None,message.content, usage.prompt_tokens,usage.completion_tokens, duration_ms
                )
            )
            logger.info("step = %d финальный ответ", step)
            return {"answer": message.content,"usage": usage_total, "steps": step +1,"trace": trace}
        print("TOOL_CALLS=",len(message.tool_calls))
        for call in message.tool_calls:
            name = call.function.name
            raw_args = call.function.arguments
            result = await _dispatch(name, raw_args)
            trace.append(
                _trace_entry(
                    step, name, raw_args, result, usage.prompt_tokens,usage.completion_tokens, duration_ms
                )
            )

            messages.append({"role": "tool", "tool_call_id": call.id, "content": result })
            logger.info("step=%d инструмент = %s -> %s", step, name, result[:300])
        result_reflect = reflect(messages, usage_total=usage_total)
        print("RESULT_REFLECT=", result_reflect.status)
        if result_reflect.status == "REVISE" and revisions_used < max_revisions:
            revisions_used += 1
            logger.info("react.revision_triggered %d %s", revisions_used, result_reflect.reason)

            # Добавляем жесткую системную инструкцию для следующего шага основного агента
            messages.append({
                "role": "system",
                "content": f"Внимание, шаг заблокирован критиком! Причина: {result_reflect.reason}. Исправь свои действия на этом шаге."
            })

        if time.monotonic() - t0 > timeout_per_iteration_sec:
            return {"answer": "Timeout", "usage": usage_total, "steps": step +1,"trace": trace}
    logger.warning("исчерпан лимит шагов max_iterations=%d", max_iterations)
    return {"answer": "Превышен лимит итераций", "usage" : usage_total, "steps":max_iterations, "trace": trace}

async def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Наивный агент на Chat Completions")
    parser.add_argument("task",help="Задача для агента")
    parser.add_argument("--max-steps", type=int, default=6, help="Лимит шагов (guardrail)")
    parser.add_argument("--model", default="gpt-4o-mini", help="Модель Chat Completions")
    parser.add_argument("--trace", default=True,action="store_true", help="Печатать пошаговую трассу")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = await run_agent(args.task, max_iterations=args.max_steps, model=args.model)

    if result.get("error"):
        print(f"Остановка: {result['error']} (шагов: {result['step']})")
    else:
        print(result["answer"])

    print(result["usage"])

    if args.trace:
        print("\n--- trace ---")
        for entry in result["trace"]:
            print(json.dumps(entry, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    # Запускаем асинхронный main() через asyncio.run и передаем результат в SystemExit
    sys.exit(asyncio.run(main()))