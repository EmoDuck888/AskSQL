"""Settings validation routes."""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from app.core.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Settings"])


class ValidateKeyRequest(BaseModel):
    api_key: str
    vendor: str = "openai"
    model: str = "deepseek-chat"


@router.post("/settings/validate-api-key")
async def validate_api_key(request: ValidateKeyRequest):
    """Validate an LLM provider API key by making a minimal completion call."""
    try:
        from openai import AsyncOpenAI

        base_url = None
        if request.vendor in ("deepseek", "openai") and settings.LLM_BASE_URL:
            base_url = settings.LLM_BASE_URL

        client = AsyncOpenAI(
            api_key=request.api_key,
            base_url=base_url,
        )

        # Minimal 1-token completion to verify key
        resp = await client.chat.completions.create(
            model=request.model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=1,
        )
        return {"valid": True}
    except Exception as e:
        logger.warning("API key validation failed: %s", e)
        return {"valid": False, "error": str(e)}
