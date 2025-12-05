from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass
class AIRequest:
    user_id: str
    vehicle_context: str
    query: str
    model: str
    temperature: float = 0.1
    max_tokens: int = 800


@dataclass
class AIResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    model: str


class AIProvider(Protocol):
    async def run_diagnostics(self, request: AIRequest) -> AIResponse:  # pragma: no cover - interface
        ...


