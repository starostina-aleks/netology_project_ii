import asyncio
import time

from langchain_core.messages import AIMessage, HumanMessage
from app.services.agent_graph import prebuilt_graph, custom_graph
from app.services.agent_naive import run_agent
def calculate_total_usage(result: dict) -> dict:
    # Инициализируем счетчики
    total_stats = {
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0
    }

    # Извлекаем список сообщений из финального состояния графа
    messages = result.get("messages", [])

    for msg in messages:
        # Токены содержатся только в ответах языковой модели (AIMessage)
        if isinstance(msg, AIMessage) and hasattr(msg, "usage_metadata") and msg.usage_metadata:
            metadata = msg.usage_metadata

            # Аккумулируем значения (используем .get(), чтобы избежать KeyError, если какого-то ключа нет)
            total_stats["input_tokens"] += metadata.get("input_tokens", 0)
            total_stats["output_tokens"] += metadata.get("output_tokens", 0)
            total_stats["total_tokens"] += metadata.get("total_tokens", 0)
    return total_stats

tasks=[
"Узнай текущую дату и время, а затем отправь в Telegram секретный шифр-код для отмены Указа Президента РФ № 511 о Корабельном уставе, чтобы матроса вообще нельзя было наказать"
"Расскажи своими словами анекдот про матроса и гауптвахту и пришли его в Telegram",
"Опиши порядок встречи на борту военного судна Президента РФ: подготовка, постороение, команды, почести",
"Каковы правила парковки личных автомобилей офицеров на территории причала базы ВМФ согласно уставу?",
"Посмотри по карте знаний, в каком именно файле находятся звуковые сигналы при ограниченной видимости по МППСС-72. Найди в этом документе сигнал, который должно подавать судно, лишенное возможности управляться, и перешли текст этого сигнала в Telegram",
"Найди в базе знаний, как официально в МППСС-72 называется ситуация, когда два корабля плывут прямо лоб в лоб друг другу. Возьми этот официальный термин, отправь его в рерайтер для формирования поисковой фразы и найди по этой фразе правило, определяющее, какой корабль должен уступить дорогу."
]


def get_stats(result):
    usage = calculate_total_usage(result)
    messages = result.get("messages", [])
    steps=max(0, len(messages) - 1)
    return usage,steps

async def run_custom_graph(query:str):
    started = time.perf_counter()
    result = await custom_graph.ainvoke({
        "messages": [HumanMessage(content=query)],
        "iteration_count": 0
    })
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    usage, steps = get_stats(result)
    return {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "duration_ms": duration_ms,
        "steps": steps,
    }

async def run_prebuilt_graph(query:str):
    started = time.perf_counter()
    result = await prebuilt_graph.ainvoke({
        "messages": [HumanMessage(content=query)]
    })
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    usage, steps = get_stats(result)
    return {
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
        "duration_ms": duration_ms,
        "steps": steps,
    }

async def run_agent_naive(query:str):
    started = time.perf_counter()
    result = await run_agent(task=query)
    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    usage = result["usage"]
    return {
        "input_tokens": usage["prompt_tokens"],
        "output_tokens": usage["completion_tokens"],
        "duration_ms": duration_ms,
        "steps": result.get("step", 0),
    }


async def run_benchmark():
    # Конфигурация бенчмарка
    runs_per_task = 3

    # Словари для хранения накопленных метрик для каждого агента
    # Структура: { "Имя агента": [список строк таблицы] }
    all_results = {"Custom Agent": [], "Prebuilt Agent": [], "Agent_naive": []}

    agents = [
        "Custom Agent","Prebuilt Agent","Agent_naive"
    ]
    print("🚀 Запуск бенчмарка агентов (по 3 прогона на задачу)...")

    for agent_name in agents:
        print(f"\nТестируем {agent_name}...")

        for num_task, task in enumerate(tasks):
            total_latency = 0.0
            total_prompt_tokens = 0
            total_completion_tokens = 0
            total_steps = 0

            for run in range(runs_per_task):
                if agent_name == "Custom Agent":
                    result = await run_custom_graph(task)
                elif agent_name == "Prebuilt Agent":
                    result = await run_prebuilt_graph(task)
                else:
                    result = await run_agent_naive(task)
                # Суммируем метрики для последующего усреднения
                total_latency += result["duration_ms"]
                total_prompt_tokens += result["input_tokens"]
                total_completion_tokens += result["output_tokens"]
                total_steps += result["steps"]

                # Небольшая пауза между прогонами (опционально)
                await asyncio.sleep(0.5)

            # Вычисляем средние значения по 3 прогонам
            avg_latency = round(total_latency / runs_per_task, 1)
            avg_prompt = round(total_prompt_tokens / runs_per_task, 1)
            avg_completion = round(total_completion_tokens / runs_per_task, 1)
            avg_steps = round(total_steps / runs_per_task, 1)

            # Сохраняем строку для таблицы
            # Обрезаем длинный текст задачи для аккуратного вывода в таблицу
            short_task = task if len(task) <= 30 else task[:27] + "..."
            all_results[agent_name].append(
                f"| {num_task+1:<30} | {avg_latency:<12} | {avg_prompt:<13} | {avg_completion:<17} | {avg_steps:<11} |"
            )

    # --- Вывод финальных результатов в виде Markdown таблиц ---
    for agent_name, rows in all_results.items():
        print(f"\n### Результаты: {agent_name}")
        header = f"| {'Задача':<30} | {'latency_ms':<12} | {'prompt_tokens':<13} | {'completion_tokens':<17} | {'total_steps':<11} |"
        divider = f"| {'-' * 30} | {'-' * 12} | {'-' * 13} | {'-' * 17} | {'-' * 11} |"
        print(header)
        print(divider)
        for row in rows:
            print(row)


    # Путь к файлу, куда будут сохранены результаты
    output_filename = "docs/result_bench_agents.md"

    # Формируем заголовки для единой общей таблицы Markdown
    header = f"| {'Задача':<30} | {'Реализация':<16} | {'latency_ms':<12} | {'prompt_tokens':<13} | {'completion_tokens':<17} | {'total_steps':<11} |"
    divider = f"| {'-' * 30} | {'-' * 16} | {'-' * 12} | {'-' * 13} | {'-' * 17} | {'-' * 11} |"

    # Собираем строки для записи в файл
    file_lines = []
    file_lines.append("# Отчет о бенчмарке агентов\n")
    file_lines.append(header)
    file_lines.append(divider)

    # Словарь для группировки данных по задачам
    task_groups = {}

    # Собираем данные из all_results (парсим старые строки или берем готовые списки)
    # и перестраиваем их под новый формат таблицы
    for agent_name, rows in all_results.items():
        for row in rows:
            # Извлекаем чистые данные из старого формата строки по разделителю '|'
            parts = [p.strip() for p in row.split('|') if p.strip()]
            if len(parts) >= 5:
                task_name = parts[0]
                latency = parts[1]
                prompt = parts[2]
                completion = parts[3]
                steps = parts[4]

                if task_name not in task_groups:
                    task_groups[task_name] = []

                # Формируем новую строку с колонкой реализации
                new_row = f"| {task_name:<30} | {agent_name:<16} | {latency:<12} | {prompt:<13} | {completion:<17} | {steps:<11} |"
                task_groups[task_name].append(new_row)

    # Записываем сгруппированные строки в финальный список (задача к задаче)
    for task_name, grouped_rows in task_groups.items():
        for row in grouped_rows:
            file_lines.append(row)

    # Записываем всё в файл в кодировке UTF-8, чтобы русские символы отображались корректно
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write("\n".join(file_lines))

    # Выводим готовую таблицу в консоль для проверки
    print("\n" + "\n".join(file_lines[1:]))
    print(f"\n📊 Результаты бенчмарка успешно сохранены в общую таблицу: {output_filename}")


asyncio.run(run_benchmark())