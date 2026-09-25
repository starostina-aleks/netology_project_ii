from app.chat.repositories.pg_models  import RagQueryRow

class AdminRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory
    async def log_rag_query(
            self,question:str,confident:bool,top_score:float
    )->None:
        if self.session_factory is None:
            return
        async with self.session_factory() as s:
            s.add(
                RagQueryRow(
                    question_normalized=question.strip().lower()[:500],
                    confident=confident,
                    top_score=top_score
                )
            )
            await s.commit()