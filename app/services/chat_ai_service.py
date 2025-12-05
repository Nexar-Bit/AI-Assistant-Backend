"""AI service for chat-based conversations with message history."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.services.ai_service import AIProvider, AIResponse

logger = logging.getLogger("app.ai.chat")


@dataclass
class ChatMessage:
    """Represents a message in a chat conversation."""

    role: str  # user, assistant, system
    content: str


@dataclass
class ChatRequest:
    """Request for AI chat completion with conversation history."""

    user_id: str
    messages: List[ChatMessage]  # Full conversation history
    vehicle_context: Optional[str] = None  # Vehicle info (KM, error codes, etc.)
    model: Optional[str] = None
    temperature: float = 0.1
    max_tokens: int = 800


class ChatAIProvider:
    """Wrapper around AIProvider for chat-based conversations."""

    def __init__(self, provider: AIProvider):
        self.provider = provider

    async def chat_completion(
        self, request: ChatRequest
    ) -> tuple[AIResponse, List[Dict[str, Any]]]:
        """
        Generate AI response for a chat conversation.
        
        Returns:
            Tuple of (AIResponse, formatted_messages) where formatted_messages
            is the full conversation history formatted for OpenAI API.
        """
        # Build system message with vehicle context if provided
        system_content = (
            "You are an expert automotive diagnostic assistant for professional technicians. "
            "Provide clear, actionable diagnostic advice based on vehicle symptoms and error codes."
        )
        
        if request.vehicle_context:
            system_content += f"\n\nVehicle Context:\n{request.vehicle_context}"

        # Format messages for OpenAI API
        formatted_messages: List[Dict[str, Any]] = [
            {"role": "system", "content": system_content}
        ]
        
        # Add conversation history (excluding system messages, as we handle that above)
        for msg in request.messages:
            if msg.role != "system":  # Skip system messages from history
                formatted_messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Use the underlying provider's completion method
        # OpenAIProvider has _create_completion method
        model = request.model or getattr(self.provider, "default_model", "gpt-4o-mini")
        temperature = request.temperature
        max_tokens = request.max_tokens

        try:
            # Direct OpenAI API call via provider's _create_completion
            completion = await self.provider._create_completion(
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                messages=formatted_messages,
            )

            content = completion.choices[0].message.content or ""
            usage = completion.usage
            if usage is not None:
                prompt_tokens_used = usage.prompt_tokens
                completion_tokens_used = usage.completion_tokens
                total_tokens = usage.total_tokens
            else:
                # Fallback estimation
                prompt_tokens_used = sum(
                    len(msg.get("content", "")) // 4
                    for msg in formatted_messages
                )
                completion_tokens_used = len(content) // 4
                total_tokens = prompt_tokens_used + completion_tokens_used

            estimated_cost = self.provider._estimate_cost(
                model=model,
                prompt_tokens=prompt_tokens_used,
                completion_tokens=completion_tokens_used,
            )

            return (
                AIResponse(
                    content=content,
                    prompt_tokens=prompt_tokens_used,
                    completion_tokens=completion_tokens_used,
                    total_tokens=total_tokens,
                    estimated_cost=estimated_cost,
                    model=model,
                ),
                formatted_messages,
            )
        except (AttributeError, TypeError):
            # Fallback: combine messages into single prompt
            # Fallback: combine messages into single prompt
            combined_prompt = "\n\n".join(
                f"{msg.role.upper()}: {msg.content}" for msg in request.messages
            )
            if request.vehicle_context:
                combined_prompt = f"Vehicle Context:\n{request.vehicle_context}\n\n{combined_prompt}"
            
            # Use existing run_diagnostics method (not ideal, but works)
            from app.services.ai_service import AIRequest
            
            ai_request = AIRequest(
                user_id=request.user_id,
                vehicle_context=request.vehicle_context or "",
                query=combined_prompt,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            
            response = await self.provider.run_diagnostics(ai_request)
            
            # Format messages for return
            formatted_messages = [
                {"role": "system", "content": system_content}
            ] + [
                {"role": msg.role, "content": msg.content}
                for msg in request.messages
                if msg.role != "system"
            ]
            
            return response, formatted_messages

