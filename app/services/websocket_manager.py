"""WebSocket connection manager for real-time chat."""

import logging
from typing import Dict, Set

from fastapi import WebSocket


logger = logging.getLogger("app.websocket")


class ConnectionManager:
    """Manages WebSocket connections for real-time chat."""
    
    def __init__(self):
        # thread_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # user_id -> set of WebSocket connections (for user-specific notifications)
        self.user_connections: Dict[str, Set[WebSocket]] = {}
        # websocket -> (thread_id, user_id) mapping for cleanup
        self.connection_info: Dict[WebSocket, tuple[str, str]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        thread_id: str,
        user_id: str,
    ) -> None:
        """Accept WebSocket connection and register it."""
        await websocket.accept()
        
        # Register connection
        if thread_id not in self.active_connections:
            self.active_connections[thread_id] = set()
        self.active_connections[thread_id].add(websocket)
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)
        
        self.connection_info[websocket] = (thread_id, user_id)
        
        logger.info(
            "WebSocket connected: thread_id=%s, user_id=%s, total_connections=%d",
            thread_id,
            user_id,
            len(self.active_connections.get(thread_id, set())),
        )
    
    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection."""
        if websocket not in self.connection_info:
            return
        
        thread_id, user_id = self.connection_info[websocket]
        
        # Remove from thread connections
        if thread_id in self.active_connections:
            self.active_connections[thread_id].discard(websocket)
            if not self.active_connections[thread_id]:
                del self.active_connections[thread_id]
        
        # Remove from user connections
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(websocket)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        del self.connection_info[websocket]
        
        logger.info(
            "WebSocket disconnected: thread_id=%s, user_id=%s",
            thread_id,
            user_id,
        )
    
    async def broadcast_to_thread(
        self,
        thread_id: str,
        message: dict,
    ) -> int:
        """
        Broadcast message to all connections in a thread.
        
        Returns:
            Number of connections that received the message
        """
        if thread_id not in self.active_connections:
            return 0
        
        disconnected: Set[WebSocket] = set()
        sent_count = 0
        
        for connection in self.active_connections[thread_id]:
            try:
                await connection.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to send WebSocket message to thread %s: %s",
                    thread_id,
                    e,
                )
                disconnected.add(connection)
        
        # Clean up disconnected connections
        for conn in disconnected:
            await self.disconnect(conn)
        
        return sent_count
    
    async def send_to_user(
        self,
        user_id: str,
        message: dict,
    ) -> int:
        """
        Send message to all connections for a specific user.
        
        Returns:
            Number of connections that received the message
        """
        if user_id not in self.user_connections:
            return 0
        
        disconnected: Set[WebSocket] = set()
        sent_count = 0
        
        for connection in self.user_connections[user_id]:
            try:
                await connection.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to send WebSocket message to user %s: %s",
                    user_id,
                    e,
                )
                disconnected.add(connection)
        
        # Clean up disconnected connections
        for conn in disconnected:
            await self.disconnect(conn)
        
        return sent_count
    
    def get_thread_connection_count(self, thread_id: str) -> int:
        """Get number of active connections for a thread."""
        return len(self.active_connections.get(thread_id, set()))
    
    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of active connections for a user."""
        return len(self.user_connections.get(user_id, set()))


# Global connection manager instance
connection_manager = ConnectionManager()

