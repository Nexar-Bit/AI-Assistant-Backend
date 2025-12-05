"""AI Context Manager for maintaining conversation history and vehicle context."""

import logging
from typing import Dict, List, Optional

from app.chat import ChatThread, ChatMessage


logger = logging.getLogger("app.ai.context")


class AIContextManager:
    """Manages AI conversation context with vehicle information and message history."""

    MAX_CONTEXT_MESSAGES = 20  # Last 20 messages
    MAX_CONTEXT_TOKENS = 8000  # Model-dependent (gpt-4o-mini supports up to 128k, but we limit for cost)
    
    VEHICLE_DIAGNOSTIC_SYSTEM_PROMPT = """You are an expert automotive diagnostic assistant for professional technicians.
Your role is to help diagnose vehicle issues based on symptoms, error codes, and vehicle information.
Provide clear, actionable diagnostic advice. Use technical terminology appropriate for professional mechanics.
Always consider the vehicle's make, model, year, mileage, and any diagnostic trouble codes (DTCs) when providing recommendations."""

    def build_context(
        self,
        thread: ChatThread,
        messages: List[ChatMessage],
    ) -> List[Dict[str, str]]:
        """
        Build AI context from thread and messages.
        
        Args:
            thread: ChatThread with vehicle context
            messages: List of ChatMessage objects (should be ordered by sequence_number)
        
        Returns:
            List of formatted messages for OpenAI API
        """
        # 1. Build vehicle context string
        vehicle_context = self._build_vehicle_context(thread)
        
        # 2. Get recent messages (last MAX_CONTEXT_MESSAGES)
        recent_messages = messages[-self.MAX_CONTEXT_MESSAGES:] if len(messages) > self.MAX_CONTEXT_MESSAGES else messages
        
        # 3. Build system message with vehicle info
        system_content = f"{self.VEHICLE_DIAGNOSTIC_SYSTEM_PROMPT}\n\n{vehicle_context}"
        system_message = {
            "role": "system",
            "content": system_content
        }
        
        # 4. Format conversation history
        formatted_messages: List[Dict[str, str]] = [system_message]
        for msg in recent_messages:
            # Map our role to OpenAI role
            openai_role = "assistant" if msg.role == "assistant" else "user"
            formatted_messages.append({
                "role": openai_role,
                "content": msg.content
            })
        
        # 5. Estimate tokens and truncate if needed
        total_tokens = self._estimate_tokens(formatted_messages)
        if total_tokens > self.MAX_CONTEXT_TOKENS:
            logger.warning(
                "Context exceeds token limit (%d > %d), truncating oldest messages",
                total_tokens,
                self.MAX_CONTEXT_TOKENS
            )
            formatted_messages = self._truncate_context(formatted_messages)
        
        return formatted_messages

    def _build_vehicle_context(self, thread: ChatThread) -> str:
        """Build vehicle context string from thread data."""
        context_parts = []
        
        if thread.license_plate:
            context_parts.append(f"License Plate: {thread.license_plate}")
        
        if thread.vehicle_km:
            context_parts.append(f"Current Mileage: {thread.vehicle_km:,} KM")
        
        if thread.error_codes:
            # Parse error codes (comma-separated)
            codes = [code.strip() for code in thread.error_codes.split(",")]
            context_parts.append(f"Diagnostic Trouble Codes (DTC): {', '.join(codes)}")
        
        if thread.vehicle_context:
            context_parts.append(f"Additional Context: {thread.vehicle_context}")
        
        # Get vehicle details if vehicle_id exists (would need to fetch from DB)
        # For now, we use what's in the thread
        
        if not context_parts:
            return "Vehicle information not provided."
        
        return "\n".join(context_parts)

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """
        Estimate token count for messages.
        Uses heuristic: ~4 characters per token (conservative estimate).
        """
        total_chars = sum(len(msg.get("content", "")) for msg in messages)
        return total_chars // 4

    def _truncate_context(
        self,
        messages: List[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        """
        Truncate context to fit within token limits.
        Keeps system message and vehicle context, removes oldest user/assistant messages.
        """
        if len(messages) <= 1:
            return messages
        
        # Keep system message
        system_msg = messages[0]
        
        # Get user/assistant messages
        conversation_msgs = messages[1:]
        
        # Truncate from the beginning, keeping the most recent
        truncated = [system_msg]
        current_tokens = self._estimate_tokens([system_msg])
        
        # Add messages from newest to oldest until we hit the limit
        for msg in reversed(conversation_msgs):
            msg_tokens = self._estimate_tokens([msg])
            if current_tokens + msg_tokens <= self.MAX_CONTEXT_TOKENS:
                truncated.insert(1, msg)  # Insert after system message
                current_tokens += msg_tokens
            else:
                break
        
        return truncated

    def get_context_summary(self, thread: ChatThread, message_count: int) -> Dict:
        """Get summary of context for logging/debugging."""
        return {
            "thread_id": str(thread.id),
            "license_plate": thread.license_plate,
            "vehicle_km": thread.vehicle_km,
            "error_codes": thread.error_codes,
            "message_count": message_count,
            "max_context_messages": self.MAX_CONTEXT_MESSAGES,
            "max_context_tokens": self.MAX_CONTEXT_TOKENS,
        }

