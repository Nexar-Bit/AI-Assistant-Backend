"""WebSocket management for real-time chat."""

import logging
from typing import Any, Dict, List, Set

from fastapi import WebSocket


logger = logging.getLogger("app.chat.websocket")


class ChatWebSocketManager:
    """Manages WebSocket connections for real-time chat updates."""

    def __init__(self):
        # Stores active connections: {thread_id: {user_id: [WebSocket, ...]}}
        self.active_connections: Dict[str, Dict[str, Set[WebSocket]]] = {}

    async def connect(self, websocket: WebSocket, thread_id: str, user_id: str):
        """Establishes a new WebSocket connection."""
        await websocket.accept()
        if thread_id not in self.active_connections:
            self.active_connections[thread_id] = {}
        if user_id not in self.active_connections[thread_id]:
            self.active_connections[thread_id][user_id] = set()
        self.active_connections[thread_id][user_id].add(websocket)
        logger.info("WebSocket connected: thread_id=%s, user_id=%s", thread_id, user_id)

    async def disconnect(self, websocket: WebSocket):
        """Removes a WebSocket connection."""
        for thread_id, users in list(self.active_connections.items()):
            for user_id, connections in list(users.items()):
                if websocket in connections:
                    connections.remove(websocket)
                    if not connections:
                        del self.active_connections[thread_id][user_id]
                    if not self.active_connections[thread_id]:
                        del self.active_connections[thread_id]
                    logger.info("WebSocket disconnected: thread_id=%s, user_id=%s", thread_id, user_id)
                    return

    async def send_personal_message(self, message: str, websocket: WebSocket):
        """Sends a message to a specific WebSocket connection."""
        await websocket.send_text(message)

    async def broadcast_to_thread(self, thread_id: str, message: Dict[str, Any]) -> int:
        """
        Broadcasts a JSON message to all active connections within a specific thread.
        
        Returns:
            Number of connections that received the message
        """
        if thread_id not in self.active_connections:
            return 0

        disconnected_websockets: List[WebSocket] = []
        sent_count = 0
        
        for user_id, connections in self.active_connections[thread_id].items():
            for connection in list(connections):  # Iterate over a copy to allow modification
                try:
                    await connection.send_json(message)
                    sent_count += 1
                except RuntimeError as e:
                    logger.warning(
                        "Failed to send WebSocket message to thread %s, user %s: %s",
                        thread_id, user_id, e
                    )
                    disconnected_websockets.append(connection)
                except Exception as e:
                    logger.error(
                        "Unexpected error sending WebSocket message to thread %s, user %s: %s",
                        thread_id, user_id, e, exc_info=True
                    )
                    disconnected_websockets.append(connection)
        
        # Clean up disconnected websockets
        for ws in disconnected_websockets:
            await self.disconnect(ws)
        
        return sent_count


# Global WebSocket manager instance
connection_manager = ChatWebSocketManager()

