import hashlib
import anyio
import json
from collections.abc import AsyncIterator
from tenacity import retry, stop_after_attempt, wait_exponential
from app.schemas.chat import ChatRequest, ChatResponse, Usage, ChatDelta
import time
import structlog
from app.observability.pii import redact_pii,prompt_hash
from app.observability.presidio import redact_pii_presidio



from app.core.exceptions import (
    LLMAuthError,
    LLMContentFilterError,
    LLMError,
    LLMRateLimitError,
    LLMTimeoutError,
)
try:
    from openai import (
        APIConnectionError,
        APITimeoutError,
        AuthenticationError,
        BadRequestError,
        RateLimitError,
    )
except ImportError:
    APIConnectionError = APITimeoutError = AuthenticationError = BadRequestError = RateLimitError = ()  # type: ignore


logger = structlog.get_logger()

class LLMService:
    def __init__(self, llm, cache, ttl: int = 3600):
        self.llm = llm
        self.cache = cache
        self.ttl = ttl

    def _key(self, req: ChatRequest) -> str:
        payload = req.model_dump(exclude={"user_id","session_id","stream"})
        blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return "chat:" + hashlib.sha256(blob.encode()).hexdigest()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def _call(self, req: ChatRequest) -> ChatResponse:
        try:
            t0 = time.perf_counter()
            raw = await self.llm.chat.completions.create(
                model=req.model,
                messages=[m.model_dump() for m in req.messages],
                temperature=req.temperature,
                max_tokens=req.max_tokens,
            )
            latency_ms = (time.perf_counter() - t0) * 1000
            resp=ChatResponse.from_openai(raw)
            #clean_text_reg = redact_pii(req.messages[-1].content)
            clean_text_presidio = await anyio.to_thread.run_sync(redact_pii_presidio, req.messages[-1].content)
            logger.info(
                "llm_request_completed",
                prompt_hash=prompt_hash(req.messages[-1].content),
                prompt_preview=clean_text_presidio[:120],
                input_tokens=resp.usage.prompt_tokens,
                output_tokens=resp.usage.completion_tokens,
                latency_ms=round(latency_ms, 2),
                finish_reason=resp.finish_reason
            )
            return resp
        except RateLimitError as e:
            raise LLMRateLimitError(str(e)) from e
        except AuthenticationError as e:
            raise LLMAuthError(str(e)) from e
        except APITimeoutError as e:
            raise LLMTimeoutError(str(e)) from e
        except BadRequestError as e:
            msg = str(e).lower()
            if "content" in msg and ("filter" in msg or "policy" in msg):
                raise LLMContentFilterError(str(e)) from e
            raise LLMError(str(e)) from e
        except APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e

    async def complete(self, req: ChatRequest) -> ChatResponse:
        # Кешируем только детерминированные ответы и при наличии кеша.
        if req.temperature > 0 or self.cache is None:
            resp = await self._call(req)
            resp.cached = False
            return resp

        key = self._key(req)
        blob = await self.cache.get(key)
        if blob:
            resp = ChatResponse.model_validate_json(blob)
            resp.cached = True
            return resp


        resp = await self._call(req)

        resp.cached = False
        await self.cache.setex(key, self.ttl, resp.model_dump_json())
        return resp

    async def stream(self, req: ChatRequest) -> AsyncIterator[ChatDelta]:
        stream = await self.llm.chat.completions.create(
            model=req.model,
            messages=[m.model_dump() for m in req.messages],
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if getattr(chunk, "choices", None):
                delta = chunk.choices[0].delta
                if getattr(delta, "content", None):
                    yield ChatDelta(content=delta.content)
            if getattr(chunk, "usage", None):
                yield ChatDelta(usage=Usage.from_openai(chunk.usage))