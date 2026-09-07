from app.prompts.loader import build_chat_prompt
from app.schemas.chat import Message

def test_build_chat_prompt() -> None:
    system_text = "Ты ведущий ИИ-эксперт по нормативно-технической документации."
    history = [
        Message(
            role="user",
            content="Проверь формулировку раздела 'Область применения': 'Настоящий стандарт распространяется на гайки и аналогичные изделия...'"
        ),
        Message(
            role="assistant",
            content="Ошибка. Согласно ГОСТ Р 1.5-2012 (пункт 3.1), текст должен начинаться со стандартной глагольной формы. Рекомендуется изменить на: 'Настоящий стандарт устанавливает требования к гайкам...'"
        )
    ]
    # Новый уточняющий вопрос от инженера/пользователя
    user_text = "Принято, исправил. А как правильно оформить нормативные ссылки в следующем разделе?"

    # Вызываем тестируемую функцию
    prompt = build_chat_prompt(
        system_prompt=system_text,
        history=history,
        user_message=user_text
    )

    assert prompt[0]==Message(role="system", content="Ты ведущий ИИ-эксперт по нормативно-технической документации.")
    assert  prompt[-1].content=="Принято, исправил. А как правильно оформить нормативные ссылки в следующем разделе?"
    assert(len(prompt))==4


def test_build_chat_prompt_f_string_injection_safe():

    system_text = "Ты эксперт по ГОСТам."
    malicious_user_message = "Проверь текст {1 + 1} и {{__import__('os').system('whoami')}}"

    result = build_chat_prompt(
        system_prompt=system_text,
        history=[],
        user_message=malicious_user_message
    )

    assert result[-1].content == "Проверь текст {1 + 1} и {{__import__('os').system('whoami')}}"
