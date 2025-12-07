from __future__ import annotations

import logging
from typing import Any, Dict, Callable, Type

try:  # optional dependency so global Python can still run
    import tiktoken  # type: ignore
except ImportError:  # pragma: no cover - fallback
    tiktoken = None  # type: ignore[assignment]

try:
    from openai import AsyncOpenAI, RateLimitError  # type: ignore
except Exception:  # pragma: no cover - allow app to start without modern openai
    AsyncOpenAI = None  # type: ignore[assignment]

    class RateLimitError(Exception):  # fallback type
        ...

try:
    from tenacity import (  # type: ignore
        retry,
        retry_if_exception_type,
        stop_after_attempt,
        wait_exponential_jitter,
    )
except ImportError:  # pragma: no cover - fallback, no-op retry
    def retry_if_exception_type(exc_type: Type[BaseException]) -> Callable[..., bool]:  # type: ignore[override]
        def predicate(exc: BaseException) -> bool:
            return isinstance(exc, exc_type)

        return predicate

    def stop_after_attempt(max_attempts: int) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return wrapper

    def wait_exponential_jitter(**_: Any) -> Callable[..., Any]:
        def wrapper(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return wrapper

    def retry(*args: Any, **kwargs: Any) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            return fn

        return decorator

from app.core.config import settings
from app.services.ai_service import AIProvider, AIRequest, AIResponse
from app.services.prompts import build_vehicle_diagnostics_prompt


logger = logging.getLogger("app.ai.openai")


MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # prices per 1K tokens in USD (adjust as needed)
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


class OpenAIProvider(AIProvider):
    # Class-level cache for encodings to avoid repeated downloads
    _encoding_cache: Dict[str, Any] = {}

    def __init__(self, api_key: str, default_model: str = "gpt-4o-mini") -> None:
        if AsyncOpenAI is None:
            raise RuntimeError(
                "OpenAI client is not available. Please install 'openai>=1.55.3' "
                "in this Python environment to use AI features. "
                "This version is required for compatibility with httpx 0.28.x."
            )
        try:
            self.client = AsyncOpenAI(api_key=api_key)
        except (TypeError, AttributeError) as e:
            logger.error(
                f"OpenAI client initialization failed: {e}. "
                "This is likely a version compatibility issue. "
                "Please ensure openai>=1.55.3 is installed."
            )
            raise RuntimeError(
                "Failed to initialize OpenAI client. "
                "Please upgrade to openai>=1.55.3 for compatibility with httpx 0.28.x."
            ) from e
        self.default_model = default_model

    def _get_encoding(self, model: str):
        """
        Get tiktoken encoding for a model, with caching and error handling.
        Falls back to default encoding or None if all attempts fail.
        """
        if tiktoken is None:
            return None

        # Check cache first
        if model in self._encoding_cache:
            return self._encoding_cache[model]

        # Try to get encoding for the specific model
        try:
            encoding = tiktoken.encoding_for_model(model)
            self._encoding_cache[model] = encoding
            return encoding
        except KeyError:
            # Model not found, try default encoding
            logger.debug("Model %s not found in tiktoken registry, trying default encoding", model)
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                self._encoding_cache[model] = encoding
                return encoding
            except Exception as e:
                logger.warning(
                    "Failed to get cl100k_base encoding: %s. Will use fallback estimation.",
                    str(e),
                )
                return None
        except Exception as e:
            # Handle connection errors, network issues, etc.
            logger.warning(
                "Failed to load tiktoken encoding for model %s (connection error): %s. "
                "Trying fallback encoding.",
                model,
                str(e),
            )
            # Try to use a default encoding as fallback
            try:
                encoding = tiktoken.get_encoding("cl100k_base")
                self._encoding_cache[model] = encoding
                return encoding
            except Exception as fallback_error:
                logger.warning(
                    "Failed to get fallback encoding: %s. Will use character-based estimation.",
                    str(fallback_error),
                )
                return None

    def _estimate_tokens(self, model: str, text: str) -> int:
        """
        Estimate token count for text.
        Falls back to character-based estimation if tiktoken is unavailable or fails.
        """
        if tiktoken is None:
            # Simple fallback: ~4 characters per token (conservative estimate)
            return max(1, len(text) // 4)
        
        try:
            enc = self._get_encoding(model)
            if enc is None:
                # Fallback to character-based estimation
                return max(1, len(text) // 4)
            return len(enc.encode(text))
        except Exception as e:
            # If encoding fails for any reason, use fallback
            logger.warning(
                "Token estimation failed for model %s: %s. Using fallback estimation.",
                model,
                str(e),
            )
            return max(1, len(text) // 4)

    def _estimate_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        pricing = MODEL_PRICING.get(model, MODEL_PRICING.get("gpt-4o-mini", {}))
        in_price = pricing.get("input", 0.0)
        out_price = pricing.get("output", 0.0)
        return (prompt_tokens / 1000.0) * in_price + (completion_tokens / 1000.0) * out_price

    @retry(
        retry=retry_if_exception_type(RateLimitError),
        wait=wait_exponential_jitter(initial=1, max=10),
        stop=stop_after_attempt(3),
        reraise=True,
    )
    async def _create_completion(self, **kwargs: Any):
        return await self.client.chat.completions.create(**kwargs)

    async def run_diagnostics(self, request: AIRequest) -> AIResponse:
        model = request.model or self.default_model

        prompt = build_vehicle_diagnostics_prompt(
            vehicle_context=request.vehicle_context,
            user_query=request.query,
        )

        prompt_tokens = self._estimate_tokens(model, prompt)

        logger.info(
            "openai_request",
            extra={
                "model": model,
                "user_id": request.user_id,
                "prompt_tokens_estimate": prompt_tokens,
            },
        )

        completion = await self._create_completion(
            model=model,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert automotive diagnostic assistant for professional technicians.",
                },
                {"role": "user", "content": prompt},
            ],
        )

        content = completion.choices[0].message.content or ""
        usage = completion.usage
        if usage is not None:
            prompt_tokens_used = usage.prompt_tokens
            completion_tokens_used = usage.completion_tokens
            total_tokens = usage.total_tokens
        else:
            completion_tokens_used = self._estimate_tokens(model, content)
            prompt_tokens_used = prompt_tokens
            total_tokens = prompt_tokens_used + completion_tokens_used

        estimated_cost = self._estimate_cost(
            model=model,
            prompt_tokens=prompt_tokens_used,
            completion_tokens=completion_tokens_used,
        )

        logger.info(
            "openai_response",
            extra={
                "model": model,
                "user_id": request.user_id,
                "prompt_tokens": prompt_tokens_used,
                "completion_tokens": completion_tokens_used,
                "total_tokens": total_tokens,
                "estimated_cost": estimated_cost,
            },
        )

        return AIResponse(
            content=content,
            prompt_tokens=prompt_tokens_used,
            completion_tokens=completion_tokens_used,
            total_tokens=total_tokens,
            estimated_cost=estimated_cost,
            model=model,
        )


