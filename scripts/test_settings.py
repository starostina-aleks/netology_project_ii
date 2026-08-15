from app.core.config import get_settings
from app.chat.deps import ChatServiceDep
from app.chat.routes import create_chat,CreateChatIn
settings=get_settings()
print(settings.chat_context_strategy)
chat_data = CreateChatIn(
    owner_external_id="test-1",
    interface="cli"
)

create_chat(chat_data,chat_service=ChatServiceDep())