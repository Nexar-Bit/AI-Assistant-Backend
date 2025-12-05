# Real-Time Chat Architecture Design

## Overview

This document outlines the real-time chat architecture for the Vehicle Diagnostics AI Platform, including WebSocket support, message structure, and AI context management.

---

## 1. Chat Session Entity (ChatThread)

### Current Implementation
- ✅ `chat_threads` table exists
- ✅ Fields: `id`, `workshop_id`, `user_id`, `vehicle_id`, `license_plate`
- ✅ Token tracking: `total_prompt_tokens`, `total_completion_tokens`, `total_tokens`
- ✅ Status: `is_resolved`, `is_archived`

### Enhancements Needed
- [ ] Add `status` enum field (active, completed, archived)
- [ ] Add `last_message_at` timestamp
- [ ] Add `session_metadata` JSONB for flexible extensions

### Schema Enhancement
```sql
ALTER TABLE chat_threads 
  ADD COLUMN status VARCHAR(20) DEFAULT 'active' CHECK (status IN ('active', 'completed', 'archived')),
  ADD COLUMN last_message_at TIMESTAMPTZ,
  ADD COLUMN session_metadata JSONB DEFAULT '{}';
```

---

## 2. Message Structure (ChatMessage)

### Current Implementation
- ✅ `chat_messages` table exists
- ✅ Fields: `id`, `thread_id`, `user_id`, `role`, `content`
- ✅ AI metadata: `ai_model_used`, `prompt_tokens`, `completion_tokens`, `estimated_cost`
- ✅ Ordering: `sequence_number`

### Enhancements Needed
- [ ] Add `sender_type` enum (technician, ai, system)
- [ ] Add `attachments` JSONB for images, error codes, diagnostic files
- [ ] Add `message_metadata` JSONB for flexible extensions
- [ ] Support markdown content rendering

### Schema Enhancement
```sql
ALTER TABLE chat_messages
  ADD COLUMN sender_type VARCHAR(20) DEFAULT 'technician' CHECK (sender_type IN ('technician', 'ai', 'system')),
  ADD COLUMN attachments JSONB DEFAULT '[]',
  ADD COLUMN message_metadata JSONB DEFAULT '{}',
  ADD COLUMN is_markdown BOOLEAN DEFAULT true;
```

---

## 3. AI Context Management

### Requirements
- Maintain conversation history (last 20 messages)
- Include vehicle context in each AI request
- Track token usage per message
- Support context window management

### Implementation Strategy

#### Context Window Management
```python
class AIContextManager:
    MAX_CONTEXT_MESSAGES = 20
    MAX_CONTEXT_TOKENS = 8000  # Model-dependent
    
    def build_context(self, thread: ChatThread, messages: List[ChatMessage]) -> List[Dict]:
        # 1. Get vehicle context
        vehicle_context = self._build_vehicle_context(thread)
        
        # 2. Get recent messages (last 20)
        recent_messages = messages[-self.MAX_CONTEXT_MESSAGES:]
        
        # 3. Build system message with vehicle info
        system_message = {
            "role": "system",
            "content": f"{VEHICLE_DIAGNOSTIC_SYSTEM_PROMPT}\n\n{vehicle_context}"
        }
        
        # 4. Format conversation history
        formatted_messages = [system_message]
        for msg in recent_messages:
            formatted_messages.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # 5. Check token limits
        total_tokens = self._estimate_tokens(formatted_messages)
        if total_tokens > self.MAX_CONTEXT_TOKENS:
            # Truncate oldest messages, keep system + vehicle context
            formatted_messages = self._truncate_context(formatted_messages)
        
        return formatted_messages
```

---

## 4. Real-Time Communication (WebSocket)

### Architecture

```
Client (Browser)
    ↓ WebSocket Connection
FastAPI WebSocket Endpoint
    ↓ Message Queue
AI Service
    ↓ Response
WebSocket Broadcast
    ↓
All Connected Clients (same thread)
```

### WebSocket Endpoint Design

```python
@router.websocket("/ws/chat/{thread_id}")
async def chat_websocket(
    websocket: WebSocket,
    thread_id: str,
    current_user: User = Depends(get_current_user_ws),
):
    """
    WebSocket endpoint for real-time chat.
    
    Message Format (Client → Server):
    {
        "type": "message",
        "content": "User message text",
        "attachments": [...]
    }
    
    Message Format (Server → Client):
    {
        "type": "message" | "typing" | "error" | "status",
        "message": {...ChatMessage...},
        "thread": {...ChatThread...},
        "timestamp": "2025-01-XX..."
    }
    """
```

### Connection Management

```python
class ConnectionManager:
    def __init__(self):
        # thread_id -> set of WebSocket connections
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        # user_id -> set of WebSocket connections
        self.user_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, thread_id: str, user_id: str):
        await websocket.accept()
        if thread_id not in self.active_connections:
            self.active_connections[thread_id] = set()
        self.active_connections[thread_id].add(websocket)
        
        if user_id not in self.user_connections:
            self.user_connections[user_id] = set()
        self.user_connections[user_id].add(websocket)
    
    async def disconnect(self, websocket: WebSocket, thread_id: str, user_id: str):
        self.active_connections[thread_id].discard(websocket)
        self.user_connections[user_id].discard(websocket)
    
    async def broadcast_to_thread(self, thread_id: str, message: dict):
        if thread_id in self.active_connections:
            disconnected = set()
            for connection in self.active_connections[thread_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.add(connection)
            for conn in disconnected:
                self.active_connections[thread_id].discard(conn)
```

---

## 5. Message Flow

### User Sends Message

```
1. User types message in frontend
2. Frontend sends via WebSocket:
   {
     "type": "message",
     "content": "Engine is misfiring",
     "attachments": []
   }
3. Backend receives WebSocket message
4. Backend saves user message to database
5. Backend broadcasts "typing" indicator to all clients
6. Backend calls AI service with context
7. AI service processes request
8. Backend saves AI response to database
9. Backend broadcasts both messages to all connected clients
10. Frontend updates UI with new messages
```

### AI Response Streaming (Future Enhancement)

```
1. Backend receives user message
2. Backend calls AI service with streaming=True
3. AI service streams tokens as they're generated
4. Backend forwards each token chunk via WebSocket
5. Frontend displays streaming text (like ChatGPT)
```

---

## 6. Attachment Support

### Supported Types
- **Images**: Diagnostic photos, error code screenshots
- **Error Codes**: DTC codes (P0301, P0302, etc.)
- **Diagnostic Files**: OBD-II logs, scan tool exports

### Storage Strategy
```python
# Option A: Store in database (JSONB)
attachments = [
    {
        "type": "image",
        "url": "/uploads/threads/{thread_id}/image_123.jpg",
        "filename": "engine_bay.jpg",
        "size": 245678,
        "mime_type": "image/jpeg"
    },
    {
        "type": "error_code",
        "code": "P0301",
        "description": "Cylinder 1 Misfire Detected"
    }
]

# Option B: Store file references only
attachments = [
    {
        "type": "file",
        "file_id": "uuid-of-file-record",
        "filename": "obd_scan.log"
    }
]
```

---

## 7. Status Management

### Thread Status Lifecycle

```
active → completed → archived
  ↓         ↓
  └─────────┘ (can be reactivated)
```

- **active**: Ongoing conversation, accepting new messages
- **completed**: Issue resolved, no new messages expected
- **archived**: Historical record, read-only

### Status Transitions
- Auto-complete: After 7 days of inactivity
- Manual: User/admin can change status
- System: Auto-archive after 30 days of completion

---

## 8. Performance Considerations

### Database Indexing
```sql
-- Fast thread lookup
CREATE INDEX idx_chat_threads_status_workshop 
  ON chat_threads(workshop_id, status, last_message_at DESC);

-- Fast message retrieval
CREATE INDEX idx_chat_messages_thread_sequence 
  ON chat_messages(thread_id, sequence_number);

-- Fast user thread lookup
CREATE INDEX idx_chat_threads_user_status 
  ON chat_threads(user_id, status, last_message_at DESC);
```

### Caching Strategy
- Cache last 20 messages per thread in Redis
- TTL: 5 minutes
- Invalidate on new message

### Connection Limits
- Max 10 WebSocket connections per user
- Max 50 connections per thread
- Rate limit: 10 messages per minute per user

---

## 9. Security Considerations

### WebSocket Authentication
```python
async def get_current_user_ws(
    websocket: WebSocket,
    token: str = Query(...),
) -> User:
    """Authenticate WebSocket connection via query parameter token."""
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload["sub"])
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            await websocket.close(code=1008, reason="Unauthorized")
            return None
        return user
    except:
        await websocket.close(code=1008, reason="Invalid token")
        return None
```

### Authorization
- Verify user is member of thread's workshop
- Verify user has permission to send messages (not viewer role)
- Rate limit per user to prevent abuse

---

## 10. Implementation Checklist

### Backend
- [ ] Add status field to ChatThread model
- [ ] Add sender_type and attachments to ChatMessage model
- [ ] Create AIContextManager service
- [ ] Implement WebSocket endpoint
- [ ] Create ConnectionManager class
- [ ] Add database indexes
- [ ] Implement attachment storage (local/S3)
- [ ] Add rate limiting for WebSocket

### Frontend
- [ ] WebSocket client connection
- [ ] Real-time message display
- [ ] Typing indicators
- [ ] Attachment upload UI
- [ ] Markdown rendering for messages
- [ ] Connection status indicator
- [ ] Auto-reconnect on disconnect

### Testing
- [ ] WebSocket connection test
- [ ] Multi-client message broadcast
- [ ] AI context management test
- [ ] Attachment upload/download test
- [ ] Rate limiting test
- [ ] Connection cleanup test

---

## Summary

**Architecture**: WebSocket-based real-time chat with AI context management
**Message Structure**: Enhanced with sender_type, attachments, metadata
**Context Management**: Last 20 messages + vehicle context, token-aware
**Status Tracking**: active → completed → archived lifecycle
**Security**: Token-based WebSocket auth, workshop-level authorization

**Status**: Design Complete, Ready for Implementation

