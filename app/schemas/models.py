from pydantic import BaseModel
class ModelInfo(BaseModel):
    name: str
    input_per_1m: float = 0.0
    output_per_1m: float = 0.0
    cached: float = 0.0
    context_window: int | None = None




