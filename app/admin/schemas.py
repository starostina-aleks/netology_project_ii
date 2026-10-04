from datetime import datetime
from pydantic import BaseModel,Field

class TopQuestion(BaseModel):
    question: str
    count: int

class StatsOut(BaseModel):
    total_messages:int
    active_users:int
    feedback_ratio:float=0.0
    questions:list[TopQuestion] = Field(default_factory=list)

class UserStats(BaseModel):
    user_id: str
    chats_count: int
    last_seen_at: datetime

class BroadcastIn(BaseModel):
    text: str
    owner_ids: list[int] | None = None
    interface: str | None = None

class BroadcastResult(BaseModel):
    sent: int
    failed: int

class ExportItem(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    created_at: str

class ExportResult(BaseModel):
    items: list[ExportItem]
    next_after: datetime | None = None

class AlertOut(BaseModel):
    id: int
    kind: str
    payload: dict

class HandoffIn(BaseModel):
    owner_external_id: str
    interface: str ="telegram"
    status:str #"active", "paused_for_human", "resolved"


