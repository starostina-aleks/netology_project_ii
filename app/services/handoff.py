from uuid import UUID
from sqlalchemy import text

VALID_STATUSES = ("active", "paused_for_human", "resolved")


async def set_handoff_status(
        session_factory, chat_id: UUID, status:str
)->None:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid handoff status: {repr(status)}; must be one of {VALID_STATUSES}"
        )
    if session_factory is None:
        return
    async with session_factory() as session:
        await session.execute(
        text(""
             "UPDATE CHATS SET handoff_status = :s"
             "WHERE chat_id = :id "
             ),
        {"s": status,"id": chat_id}
        )
        await session.commit()

async def set_handoff_status_by_owner(
        session_factory,
        owner_external_id :str,
        interface: str,
        status: str
) -> int:
    if status not in VALID_STATUSES:
        raise ValueError(
            f"invalid handoff status: {status}; must be one of {VALID_STATUSES}"
        )
    if session_factory is None:
        return 0
    async with session_factory() as session:
        result=await session.execute(
            text(""
                 "UPDATE CHATS SET handoff_status = :s "
                 "WHERE owner_external_id= :o "
                 "and interface = :i "
                 ),
            {"s": status, "o": owner_external_id, "i": interface}
        )
        await session.commit()
        return result.rowcount or 0
