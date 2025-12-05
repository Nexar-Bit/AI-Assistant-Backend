from __future__ import annotations

from app.services.ai_service import AIProvider, AIRequest, AIResponse


class LocalAIProvider(AIProvider):
    """Placeholder for future on-prem/local LLM implementation."""

    async def run_diagnostics(self, request: AIRequest) -> AIResponse:  # pragma: no cover - placeholder
        raise NotImplementedError("Local AI provider is not implemented yet.")


