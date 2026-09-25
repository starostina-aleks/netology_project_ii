from phoenix.client import Client
from phoenix.evals import LLM, evaluate_dataframe
from phoenix.evals.metrics.faithfulness import FaithfulnessEvaluator
from app.core.config import get_settings
import json
import re

settings=get_settings()
client = Client()
df = client.spans.get_spans_dataframe(project_name="default")
rag_df = df[df["span_kind"].str.upper() == "LLM"].copy()
def extract_text(val):
    if isinstance(val, list) and len(val) > 0:
        item = val[0]
        if isinstance(item, dict):
            # Проверяем оба возможных варианта ключа
            if "message.content" in item:
                return item["message.content"]
            if "content" in item:
                return item["content"]
    return str(val)

def get_clean_question(text):
    match = re.search(r'(?i)вопрос:\s*(.*)', text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return text.strip()

raw_input = rag_df["attributes.llm.input_messages"].apply(extract_text)
rag_df["input"] = raw_input.apply(get_clean_question)
rag_df["output"] = rag_df["attributes.llm.output_messages"].apply(extract_text)
rag_df["context"] = raw_input
llm = LLM(
    provider="openai",
    model=settings.llm.default_model,
    api_key=settings.llm.openai_api_key.get_secret_value(),
    base_url=settings.llm.base_url,
)
evaluator = FaithfulnessEvaluator(llm=llm,max_tokens=1024)
rag_df=rag_df.tail(5)
print(f"Запускаем оценку для {len(rag_df)} RAG-запросов...")
results = evaluate_dataframe(
    dataframe=rag_df,
    evaluators=[evaluator]
)
print("\nСохраняем результаты в файлы...")
full_data = results["faithfulness_score"].to_dict()


with open("tests/eval/phoenix_Hallucination_evaluator.json", "w", encoding="utf-8") as f:
    json.dump(full_data, f, ensure_ascii=False, indent=4)
print("📝 Полный JSON сохранен в: evaluation_report.json")

# Вариант 2. Сохраняем как легко читаемый текстовый отчет с обоснованием
with open("tests/eval/phoenix_Hallucination_evaluator.txt", "w", encoding="utf-8") as f:
    f.write("=" * 60 + "\n")
    f.write("📋 ПОЛНЫЙ ОТЧЕТ О ПРОВЕРКЕ ДОСТОВЕРНОСТИ (PHOENIX)\n")
    f.write("=" * 60 + "\n\n")

    for span_id, score_data in full_data.items():
        f.write(f"🔹 [ID Спана]: {span_id}\n")
        if isinstance(score_data, dict):
            f.write(f"🔹 [Метрика]:  {score_data.get('name')}\n")
            f.write(f"🔹 [Оценка]:   {score_data.get('score')}\n")
            f.write(f"🔹 [Вердикт]:  {score_data.get('label')}\n")

            # Извлекаем развернутое текстовое обоснование от модели-судьи
            explanation = score_data.get('explanation') or "Нет текстового описания"
            f.write(f"🔹 [Полное обоснование]:\n{explanation}\n")
        else:
            f.write(f"🔹 [Данные]: {score_data}\n")
        f.write("-" * 60 + "\n")

print("📄 Текстовый отчет сохранен в: evaluation_report.txt")




