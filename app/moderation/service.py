import logging
import re

from fastapi import FastAPI
from openai import AsyncOpenAI
from app.moderation.domain import ModerationResult
from app.services.alerter import fire_alert
from app.observability.pii import redact_pii,prompt_hash
import hashlib
import re

import structlog

#log=logging.getLogger(__name__)
log = structlog.get_logger()
DEFAULT_BLOCKLIST: list[str] = [
    #r"(?i)\b(как\s+(сделать|собрать|изготовить|купить))\s+(бомб[уы]|взрывчатк)"
    r"(?i)\bкак\s+(сделать|собрать|купить)\s+тест"
]


def log_incident(
        text: str,
        result: ModerationResult,
        owner_external_id: str | None,
) -> None:
    log.warning(
        "moderation_blocked",
        text_hash=prompt_hash(text),
        masked_text=redact_pii(text),
        categories=result.categories,
        layer=result.layer,
        owner_external_id=owner_external_id,
    )


class ModerationService:
    def __init__(
            self,
            llm_client: AsyncOpenAI,
            use_openai_moderation:bool=False,
            blocklist: list[str]|None=None,
            session_factory=None
    ) -> None:
        self.llm  = llm_client
        self.use_openai = use_openai_moderation
        patterns=blocklist if blocklist is not None else DEFAULT_BLOCKLIST
        self._patterns=[re.compile(p) for p in patterns]
        self.session_factory=session_factory

    async def _raise_alert(
            self,result:ModerationResult,owner_external_id:str|None
    )->None:
        if self.session_factory is None:
            return
        try:
            await fire_alert(
                self.session_factory,
                kind="moderation_block",
                payload={
                    "layer":result.layer,
                    "categories":result.categories,
                    "owner_external_id":owner_external_id,
                },
            )
        except Exception as e:
            log.warning("fire_alert(moderation_block) failed:%s",e)

    async def check_input(
        self,text:str,owner_external_id:str|None=None
    )->ModerationResult:
        if not text:
            return ModerationResult(allowed=True,layer="passed")
        for pat in self._patterns:
            if pat.search(text):
                result=ModerationResult(
                    allowed=False,
                    categories=["custom_blocklist"],
                    layer="regex")
                await self._raise_alert(result,owner_external_id)
                log_incident(
                    text,
                    result,
                    owner_external_id,
                )
                return result
        if self.use_openai:
            try:
                resp=await self.llm.moderations.create(
                    model="omni-moderation-latest",input=text
                )
                r=resp.results[0]
                if r.flagged:
                    flagged_cats=[
                        c for c,on in r.categories.model_dump().items() if on
                    ]
                    result=ModerationResult(
                        allowed=False,
                        categories=flagged_cats,
                        layer="openai",
                        scored=r.category_scores.model_dump()
                    )
                    await self._raise_alert(result,owner_external_id)
                    log_incident(
                        text,
                        result,
                        owner_external_id,
                    )
                    return result
            except Exception as e:
                log.warning("moderation Api failed:%s -fail-open",e)
        return ModerationResult(allowed=True, layer="passed")