"""Conversation context management for chat."""

import logging
from typing import Any, Dict, List

from .models import ChatThread, ChatMessage
from app.services.openai_service import OpenAIProvider
from app.services.prompt_service import build_system_prompt
from sqlalchemy.orm import Session


logger = logging.getLogger("app.chat.context")

# Max tokens for the entire context (system + history + current query)
MAX_CONTEXT_TOKENS = 8000
# Number of historical messages to consider by default
DEFAULT_HISTORY_LIMIT = 20


class ChatContextBuilder:
    """
    Manages the construction of AI conversation context.
    This includes the system prompt, vehicle-specific data, and conversation history.
    """

    def __init__(self, history_limit: int = DEFAULT_HISTORY_LIMIT):
        self.history_limit = history_limit
        self.openai_provider = OpenAIProvider(api_key="dummy_key")  # Dummy key, only for token estimation

    def _estimate_tokens(self, text: str, model: str = "gpt-4o-mini") -> int:
        """Estimate tokens using the OpenAIProvider's method."""
        return self.openai_provider._estimate_tokens(model, text)

    def build_context(
        self, 
        thread: ChatThread, 
        messages: List[ChatMessage], 
        db: Session,
        model: str = "gpt-4o-mini"
    ) -> List[Dict[str, Any]]:
        """
        Builds the full AI context for a chat completion request.
        
        Args:
            thread: The ChatThread object containing vehicle context.
            messages: A list of ChatMessage objects in chronological order.
            db: Database session for fetching prompts.
            model: The AI model to use for token estimation.
        
        Returns:
            A list of dictionaries formatted for the OpenAI API (role, content).
        """
        formatted_messages: List[Dict[str, Any]] = []

        # 1. System Prompt - Use prompt service to get global/workshop prompts
        system_content = build_system_prompt(
            db=db,
            workshop_id=str(thread.workshop_id),
            vehicle_context=thread.vehicle_context,
            error_codes=thread.error_codes,
            vehicle_km=thread.vehicle_km
        )

        formatted_messages.append({"role": "system", "content": system_content})

        # Estimate tokens for the system message
        current_tokens = self._estimate_tokens(system_content, model)

        # 2. Conversation History (last N messages, truncated if necessary)
        # Filter out system messages from history, as we construct the main one above
        history_messages = [
            msg for msg in messages if msg.role != "system"
        ]

        # Start from the most recent messages and add them until token limit or history limit is reached
        for msg in reversed(history_messages):
            message_content = msg.content
            message_tokens = self._estimate_tokens(message_content, model)

            # If adding this message exceeds the total context limit, stop
            if current_tokens + message_tokens > MAX_CONTEXT_TOKENS:
                logger.warning(
                    "Truncating chat history for thread %s due to token limit. "
                    "Skipping message from %s (tokens: %d). Current context tokens: %d",
                    thread.id, msg.role, message_tokens, current_tokens
                )
                break
            
            # Prepend to maintain chronological order in the final list
            formatted_messages.insert(1, {"role": msg.role, "content": message_content})
            current_tokens += message_tokens
        
        logger.info(
            "AI context built for thread %s. Total tokens: %d (estimated). Messages: %d",
            thread.id, current_tokens, len(formatted_messages)
        )

        return formatted_messages

