import re
from app.observability.presidio import redact_pii_presidio
from app.core.config import get_settings
from openai import AsyncOpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
)
import structlog
logger = structlog.get_logger()

#нормализация пробелов
def _normalize_spaces(text: str) -> str:
    """Схлопывает любые последовательности пробельных символов."""
    return re.sub(r"\s+", " ", text).strip()


CLASSIFIER_PROMPT = """Determine if the model response below contains harassment, hate speech, or sexual content.

Categories to detect:
- Harassment: language that demeans, humiliates, insults, or targets individuals or groups.
- Hate Speech: content that attacks, discriminates, or incites hatred based on race, gender, religion, sexual orientation, disability, or nationality.
- Sexual Content: explicitly sexual language, graphic descriptions, pornography, or inappropriate adult topics.

Reply with a single token: SAFE or UNSAFE.

Model response:
{model_output}
"""
settings = get_settings()
client = AsyncOpenAI(
        api_key="ollama",
        base_url="http://localhost:11434/v1",
        #timeout=settings.llm.request_timeout,
        #max_retries=settings.llm.max_retries,
    )

async def is_safe_llm(text: str) -> bool:
    try:
        resp = await client.chat.completions.create(
            model="qwen3:8b",
            messages=[
                {
                    "role": "user",
                    "content": CLASSIFIER_PROMPT.format(
                        model_output=text
                    ),
                }
            ],
            max_tokens=3,
            temperature=0,
        )

        verdict = (
            resp.choices[0]
            .message.content
            .strip()
            .upper()
        )

        return verdict == "SAFE"

    except RateLimitError:
        logger.warning("classifier_rate_limited")
        return True        # fail-open

    except APITimeoutError:
        logger.warning("classifier_timeout")
        return True

    except APIConnectionError:
        logger.warning("classifier_connection_error")
        return True

    except AuthenticationError:
        logger.exception("classifier_auth_error")
        return True

    except BadRequestError:
        logger.exception("classifier_bad_request")
        return True

    except Exception:
        logger.exception("classifier_unexpected_error")
        return True

# проверка на дословное появление system_prompt в ответе
async def filter_output(answer: str, system_prompt: str, canary: str) -> str:

    normalized_answer = _normalize_spaces(answer)
    if system_prompt is not None:
        normalized_prompt = _normalize_spaces(system_prompt)
        if normalized_prompt and normalized_prompt in normalized_answer:
            raise ValueError("system prompt leakage detected")

    if canary and canary in answer:
        raise ValueError("system_prompt leakage: canary detected")

    if not await is_safe_llm(answer):
        raise ValueError("unsafe llm output")

    return redact_pii_presidio(answer)


