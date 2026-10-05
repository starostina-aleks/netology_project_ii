#исключения модерации

from app.moderation.domain import ModerationResult

class ModerationBlockedError(Exception):
    def __init__(self,result: ModerationResult):
        self.result = result
        super().__init__(f"blocked  by {result.layer}:{result.categories}")

