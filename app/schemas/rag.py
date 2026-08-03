from pydantic import BaseModel, Field

class RAGQuery(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class RAGSource(BaseModel):
    text: str
    source: str | None = None
    score: float


class RAGAnswer(BaseModel):
    answer: str
    top_score: float
    sources: list[RAGSource]