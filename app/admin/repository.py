from datetime import datetime, timedelta, UTC
from sqlalchemy import text
from app.admin.schemas import StatsOut, UserStats, ExportItem, ExportResult
from app.observability.pii import redact_pii

class AdminRepository:
    def __init__(self,session_factory):
        self.session_factory = session_factory

    async def compute_stats(self,window_hours:int=24,top_n=10)->StatsOut:
        if self.session_factory is None:
            return StatsOut(total_messages=0,active_users=0)
        since = datetime.now(UTC) - timedelta(hours=window_hours)
        async with self.session_factory() as s:
            total = await s.scalar(
                text(
                    "SELECT COUNT(*) FROM chat_messages WHERE created_at>=:since"
                ),
                {"since":since},
            )
            active = await s.scalar(
                text(
                """
                SELECT COUNT(DISTINCT c.owner_external_id) 
                FROM chats c JOIN chat_messages cm ON cm.chat_id=c.id
                WHERE cm.created_at>=:since
                """
                ),
                {"since":since},
            )
            fb = await s.execute(
                text(
                    """
                    SELECT COUNT(*) FILTER (WHERE value='up') as up,
                    COUNT(*) FILTER (WHERE value='down') as down
                    FROM message_feedback WHERE created_at>=:since
                    """
                ),
                {"since":since},
            )
            row = fb.first()
            up = (row.up if row else 0) or 0
            down = (row.down if row else 0) or 0
            ratio = up / (up + down) if (up+down)>0 else 0.0

            top_questions = await s.execute(
                text(
                    """
                    SELECT
                        trim(
                            regexp_replace(
                                regexp_replace(
                                    lower(cm.content),
                                    '[^[:alnum:][:space:]]+',
                                    ' ',
                                    'g'
                                ),
                                '[[:space:]]+',
                                ' ',
                                'g'
                            )
                        ) AS question,
                        COUNT(*) AS count
                    FROM chat_messages cm
                    WHERE cm.created_at >= :since
                      AND cm.deleted_at IS NULL
                      AND cm.role = 'user'
                    GROUP BY question
                    ORDER BY count DESC
                    LIMIT :limit
                    """
                ),
                {
                    "since": since,
                    "limit": top_n,
                },
            )

            rows = top_questions.fetchall()

            questions = [
                {
                    "question": row.question,
                    "count": row.count,
                }
                for row in rows
            ]

            return StatsOut(
                total_messages=total or 0,
                active_users=active or 0,
                feedback_ratio=ratio,
                questions=questions,

            )

    async def compute_stats_users(self,limit=50)->list[UserStats]:
        if self.session_factory is None:
            return []
        async with self.session_factory() as s:
            users = await s.execute(
                text(
                    """
                    SELECT
                        c.owner_external_id AS user_id,
                        COUNT(DISTINCT c.id) AS chats_count,
                        MAX(cm.created_at) AS last_seen_at
                    FROM chats c
                    JOIN chat_messages cm
                        ON cm.chat_id = c.id
                    WHERE cm.deleted_at IS NULL
                      AND cm.role = 'user'
                    GROUP BY c.owner_external_id
                    ORDER BY last_seen_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            )
            users_stats = [
                UserStats(
                    user_id=row.user_id,
                    chats_count=row.chats_count,
                    last_seen_at=row.last_seen_at,
                )
                for row in users.fetchall()
            ]
            return users_stats

    async def list_owner_ids_by_interface(self,interface:str)->list[int]:
        if self.session_factory is None:
            return []
        async with self.session_factory() as s:
            rows=(
                await s.execute(
                    text(
                        """SELECT DISTINCT owner_external_id 
                        FROM chats 
                        WHERE interface=:interface
                        """
                    ),
                    {"interface":interface},
                )
            ).all()
            out: list[int] = []
            for row in rows:
                try:
                    out.append(row.owner_external_id)
                except (TypeError, ValueError):
                    continue
            return out

    async def list_messages_after(
            self, after: datetime, limit: int
    )->ExportResult:
        if self.session_factory is None:
            return ExportResult(items=[],next_after=None)
        async with self.session_factory() as s:
            stmt=text(
                """
                SELECT id, chat_id, role, content, created_at 
                FROM chat_messages 
                WHERE deleted_at IS NULL
                AND (CAST(:after AS TIMESTAMPTZ) IS NULL
                OR created_at >CAST(:after AS TIMESTAMPTZ))
                LIMIT:limit
                """
            )
            rows = (
                await s.execute(stmt,{"after":after,"limit":limit})
            ) .all()
            items = [
                ExportItem(
                    id=str(row.id),
                    chat_id=str(row.chat_id),
                    role=row.role,
                    content=redact_pii(row.content),
                    created_at=row.created_at.isoformat(),
                )
                for row in rows
            ]
            return ExportResult(
                items=items,
                next_after=rows[-1].created_at if rows else None,)
