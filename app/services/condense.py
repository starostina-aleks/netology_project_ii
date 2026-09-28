from app.chat.domain import ChatMessage

CONDENSE_PROMPT =(
    "Ниже фрагмент диалога и последний вопос пользователя.\n"
    "Перепиши последний вопрос так, чтобы он был понятен без истории:"
    "подставь предмет разговора вместо местоимений, ничего не добавляя от себя.\n"
    "Если вопрос уже самодостаточен - верни его без изменений.\n"
    "Ответь ОДНОЙ строкой: только переписанный вопрос.\n\n"
    "История:\n{history}\n\nВопрос: {question}\nПереписанный вопрос:"
)

async def condense_question(
        llm_client,
        question:str,
        history:list[dict],
        model:str
)->str:
    if not history:
        return question
    lines="\n".join(f"{m}" for m in history)

    response=await llm_client.chat.completions.create(
        model=model,
        messages=[
            {
                "role":"user",
                "content":CONDENSE_PROMPT.format(history=lines,question=question),
            }
        ],
        max_tokens=2000
    )
    return (response.choices[0].message.content or "").strip() or question
