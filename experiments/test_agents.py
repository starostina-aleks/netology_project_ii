print("start import")
import asyncio
import json
from app.agents.tools import build_search_knowledge_base
from langchain_openai import ChatOpenAI
from experiments.single_agent_baseline import run_prebuilt_graph
from experiments.multi_agent_langgraph import run_supervisor
import json
from pydantic import BaseModel, Field
from openai import OpenAI
from app.core.config import get_settings
print("end import")
settings = get_settings()

llm_model = OpenAI(
        api_key=settings.llm.openai_api_key.get_secret_value(),
        base_url=settings.llm.base_url,
        #timeout=settings.llm.request_timeout,
        max_retries=settings.llm.max_retries,
    )
class EvaluationResult(BaseModel):
    score: int = Field(..., description="Финальная оценка ответа от 0 до 10")

def evaluate_rag_response(query,data,nodes) -> int:
    answer = data.get("answer", "")
    if answer == "":
        return 0
    context_chunks = []
    for node in nodes:
        if isinstance(node, dict):
            # Проверяем частые названия полей для текста в RAG (text, content, page_content)
            text = node.get("text") or node.get("content") or node.get("page_content") or str(node)
            context_chunks.append(text)
        else:
            context_chunks.append(str(node))

    context = "\n---\n".join(context_chunks)

    # 3. Формируем системный промпт для оценки
    system_prompt = (
        "Ты — беспристрастный судья для оценки качества RAG-систем. "
        "Твоя задача — оценить предоставленный ОТВЕТ на основе КОНТЕКСТА и ВОПРОСА.\n\n"
        "Критерии выставления баллов (от 0 до 10):\n"
        "- 10: Идеальный ответ. Полностью основан на контексте, нет галлюцинаций, исчерпывающе отвечает на вопрос.\n"
        "- 7-9: Хороший ответ. Релевантен, но упущена незначительная деталь или формулировка слегка неточна.\n"
        "- 4-6: Посредственный ответ. Есть сильные галлюцинации (домыслы), либо ответ слишком поверхностный и упускает суть.\n"
        "- 1-3: Плохой ответ. Почти не связан с контекстом, содержит грубые ошибки или полностью игнорирует вопрос.\n"
        "- 0: Полный провал, сплошная галлюцинация или обоснованный отказ отвечать при реальном НАЛИЧИИ нужной информации в контексте. "
        "Обрати внимание: если контекст пустой или в нем действительно нет информации для ответа, и модель честно призналась: "
        "'К сожалению, предоставленных фактов недостаточно...', то такой безопасный отказ оценивается высоко (на 10 баллов), "
        "так как модель избежала галлюцинаций."
    )

    user_content = f"ВОПРОС: {query}\n\nКОНТЕКСТ:\n{context}\n\nОТВЕТ: {answer}"

    # 4. Делаем запрос к OpenAI с гарантированным форматом ответа
    completion = llm_model.beta.chat.completions.parse(
        model="gpt-4o-mini",  # или gpt-4o
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        response_format=EvaluationResult,
        max_tokens=1024,
        temperature=0.0  # Минимизируем случайность для стабильной оценки
    )

    # 5. Возвращаем результат
    parsed_response = completion.choices[0].message.parsed
    return parsed_response.score


async def test_agents():
    '''
    from app.services.rag import RAGService
    settings = get_settings()
    rag = RAGService(settings)
    print("RAG build...")
    rag.build()
    print("test agents...")
    agent_model = ChatOpenAI(
        model=settings.llm.default_model,  # например, "gpt-4o"
        openai_api_key=settings.llm.openai_api_key,  # ваш API-ключ
        openai_api_base=settings.llm.base_url,  # базовый URL (если используете прокси/vllm)
        max_tokens=1024,
        temperature=0.0
    )
    tools = [build_search_knowledge_base(rag.answer)]
    '''
    print("start test...")

    '''
    list_queries=[
        "Каковы правила обгона судна по правому борту и какие условия необходимо учитывать при этом?",
        "Как Министерство обороны Российской Федерации применяет дисциплинарную власть в отношении военнослужащих и какие поощрения предусмотрены для них?",
        "Каковы деловые качества личного состава электромеханических боевых частей кораблей соединения и как они влияют на профессиональную подготовленность в контексте повышения эффективности боевой подготовки?",
        "Что должен сделать командир корабля в случае аварии, если он обнаружил неисправность, и как это связано с запретом на ремонтные работы?",
        "Как корабельные расписания влияют на боевые инструкции подводных лодок и какие дополнительные расписания разрабатываются для них?"
    ]
    
    list_queries = [
    "Какие требования предъявляются к прохождению обязательной психологической экспертизы для получения служебного жилья согласно Приказу МО РФ № 1280?",
    "Каков порядок и условия выплаты надбавок гражданскому персоналу, работающему на судах обеспечения ВМФ? Ссылайтесь на конкретный родительский приказ Министра обороны и номер соответствующего приложения к его Положению."
    ]
    results=[]
    for query in list_queries:
        nodes = await rag.evaluate_inputs(query)

        metrics_supervisor = await run_supervisor(agent_model,tools,query)
        metrics_supervisor["mark"] = evaluate_rag_response(query,metrics_supervisor,nodes)
        metrics_single_agent = await run_prebuilt_graph(agent_model, tools, query)
        metrics_single_agent["mark"] = evaluate_rag_response(query, metrics_single_agent, nodes)
        results.append({
        "query": query,
        "metrics_supervisor": metrics_supervisor,
        "metrics_single_agent": metrics_single_agent,
        "nodes": nodes["retrieved_contexts"],
        })
    
    output_file = "experiments/results1.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=4)
    print(f"Статистика успешно сохранена в файл {output_file}")
    '''
    output_file = "experiments/results.json"
    markdown_file_path = "experiments/metrics_comparison.md"

    with open(output_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    total_items = len(data)

    if total_items == 0:
        print("Файл JSON пуст.")
    else:
        # Словари для накопления сумм по обоим агентам
        sup = {"latency": 0, "handoff": 0, "calls": 0, "prompt": 0, "comp": 0, "total": 0, "mark": 0}
        single = {"latency": 0, "handoff": 0, "calls": 0, "prompt": 0, "comp": 0, "total": 0, "mark": 0}

        for item in data:
            #Сбор данных по supervisor
            m_sup = item.get("metrics_supervisor", {})
            sup["latency"] += m_sup.get("latency_ms", 0)
            sup["handoff"] += m_sup.get("handoff_count", 0)
            sup["calls"] += m_sup.get("llm_calls", 0)
            sup["prompt"] += m_sup.get("prompt_tokens", 0)
            sup["comp"] += m_sup.get("completion_tokens", 0)
            sup["total"] += m_sup.get("total_tokens", 0)
            sup["mark"] += m_sup.get("mark", 0)

            # Сбор данных по single_agent
            m_single = item.get("metrics_single_agent", {})
            single["latency"] += m_single.get("latency_ms", 0)
            single["handoff"] += m_single.get("handoff_count", 0)
            single["calls"] += m_single.get("llm_calls", 0)
            single["prompt"] += m_single.get("prompt_tokens", 0)
            single["comp"] += m_single.get("completion_tokens", 0)
            single["total"] += m_single.get("total_tokens", 0)
            single["mark"] += m_single.get("mark", 0)

        # Генерация содержимого Markdown
        markdown_content = f"""# Сравнительный анализ RAG-экспериментов

        *Всего обработано тестовых запросов:* **{total_items}**

        | Метрика (Среднее значение) | `metrics_supervisor` | `metrics_single_agent` |
        | :--- | :---: | :---: |
        | **Токенов на запрос** | {sup["total"] / total_items:.2f} | {single["total"] / total_items:.2f} |
        | **LLM вызовов на запрос** | {sup["calls"] / total_items:.2f} | {single["calls"] / total_items:.2f} |
        | **Задержка** | {sup["latency"] / total_items:.2f} | {single["latency"] / total_items:.2f} |
        | **Передач управления** | {sup["handoff"] / total_items:.2f} | {single["handoff"] / total_items:.2f} |
        | **Качество ответа** | {sup["mark"] / total_items:.2f} | {single["mark"] / total_items:.2f} |
        """

        # Запись в Markdown файл
        with open(markdown_file_path, "w", encoding="utf-8") as md_file:
            md_file.write(markdown_content)

        print(f"Сравнительный отчет успешно сохранен в файл {markdown_file_path}")

if __name__ == "__main__":
    asyncio.run(test_agents())

