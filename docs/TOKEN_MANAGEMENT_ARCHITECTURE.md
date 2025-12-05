# Token Management System Architecture

## Overview

Granular token accounting system with workshop-level pools, user-level allocations, role-based limits, and real-time validation.

---

## 1. Token Accounting Model

### Workshop-Level Pool

```python
class WorkshopTokenPool:
    total_tokens_allocated: int      # Monthly allocation
    tokens_used_this_month: int       # Current month usage
    tokens_remaining: int             # Calculated: allocated - used
    reset_date: datetime              # Next monthly reset date
    monthly_limit: int                # Hard limit per month
```

**Database Schema:**
- `workshops.tokens_used_this_month` (existing)
- `workshops.monthly_token_limit` (existing)
- `workshops.token_reset_date` (NEW)
- `workshops.token_allocation_date` (NEW)

### User-Level Allocation

```python
class UserTokenAllocation:
    user_id: UUID
    workshop_id: UUID
    daily_limit: int                  # From workshop pool
    tokens_used_today: int            # Today's usage
    tokens_used_this_month: int       # Month's usage
    role_based_limit: int             # Calculated from role
    reset_date: datetime              # Next daily reset
```

**Database Schema:**
- New table: `user_token_usage`
- Tracks daily and monthly usage per user per workshop

### Token Types

```python
class TokenUsage:
    input_tokens: int                 # User messages + context
    output_tokens: int                # AI responses
    total_tokens: int                 # Sum of input + output
    
    # Cost calculation
    input_cost: float                 # Based on model pricing
    output_cost: float                 # Based on model pricing
    total_cost: float                 # Sum of costs
```

**Weight System:**
- Input tokens: 1x weight
- Output tokens: 1x weight (can be adjusted for cost differences)

---

## 2. Database Schema

### New Table: `user_token_usage`

```sql
CREATE TABLE user_token_usage (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    workshop_id UUID NOT NULL REFERENCES workshops(id),
    date DATE NOT NULL,
    
    -- Daily tracking
    input_tokens_today INTEGER DEFAULT 0,
    output_tokens_today INTEGER DEFAULT 0,
    total_tokens_today INTEGER DEFAULT 0,
    
    -- Monthly tracking
    input_tokens_month INTEGER DEFAULT 0,
    output_tokens_month INTEGER DEFAULT 0,
    total_tokens_month INTEGER DEFAULT 0,
    
    -- Limits
    daily_limit INTEGER,              -- From workshop allocation
    monthly_limit INTEGER,             -- From workshop allocation
    
    -- Metadata
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(user_id, workshop_id, date)
);

CREATE INDEX idx_user_token_usage_user_workshop 
  ON user_token_usage(user_id, workshop_id, date DESC);
```

### Enhanced `workshops` Table

```sql
ALTER TABLE workshops
  ADD COLUMN token_reset_date DATE,
  ADD COLUMN token_allocation_date DATE,
  ADD COLUMN token_reset_day INTEGER DEFAULT 1; -- Day of month to reset
```

---

## 3. Token Accounting Service

### Core Service: `TokenAccountingService`

```python
class TokenAccountingService:
    """Manages token accounting at workshop and user levels."""
    
    def check_workshop_limits(self, workshop_id: UUID, tokens_needed: int) -> bool:
        """Check if workshop has enough tokens remaining."""
        
    def check_user_limits(self, user_id: UUID, workshop_id: UUID, tokens_needed: int) -> bool:
        """Check if user has enough tokens remaining (daily + role-based)."""
        
    def reserve_tokens(self, user_id: UUID, workshop_id: UUID, tokens: int) -> bool:
        """Reserve tokens before AI call (optimistic locking)."""
        
    def record_token_usage(
        self,
        user_id: UUID,
        workshop_id: UUID,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record actual token usage after AI call."""
        
    def get_user_remaining_tokens(
        self,
        user_id: UUID,
        workshop_id: UUID,
    ) -> dict:
        """Get remaining tokens for user (daily and monthly)."""
        
    def reset_daily_limits(self) -> None:
        """Reset daily limits (run via cron/scheduler)."""
        
    def reset_monthly_limits(self) -> None:
        """Reset monthly limits (run via cron/scheduler)."""
```

---

## 4. Role-Based Limits

### Limit Configuration

```python
ROLE_TOKEN_LIMITS = {
    "owner": {
        "daily_limit_multiplier": None,  # Unlimited
        "monthly_limit_multiplier": None, # Unlimited
    },
    "admin": {
        "daily_limit_multiplier": None,  # Unlimited
        "monthly_limit_multiplier": None, # Unlimited
    },
    "technician": {
        "daily_limit_multiplier": 1.0,   # 100% of workshop daily allocation
        "monthly_limit_multiplier": 1.0,  # 100% of workshop monthly allocation
    },
    "viewer": {
        "daily_limit_multiplier": 0.0,   # No AI access
        "monthly_limit_multiplier": 0.0,  # No AI access
    },
}
```

### Calculation Logic

```python
def calculate_user_daily_limit(
    workshop: Workshop,
    user_role: str,
    workshop_member_count: int,
) -> int:
    """Calculate user's daily limit from workshop pool."""
    if role in ["owner", "admin"]:
        return None  # Unlimited
    
    # Distribute workshop daily limit among technicians
    daily_workshop_limit = workshop.monthly_token_limit // 30
    technician_count = get_technician_count(workshop.id)
    
    if technician_count == 0:
        return daily_workshop_limit
    
    # Fair distribution
    return daily_workshop_limit // technician_count
```

---

## 5. Real-Time Validation

### Pre-Check Before AI Call

```python
async def validate_token_limits(
    user_id: UUID,
    workshop_id: UUID,
    estimated_tokens: int,
    db: Session,
) -> TokenValidationResult:
    """
    Validate token limits before AI call.
    
    Returns:
        TokenValidationResult with:
        - is_allowed: bool
        - reason: str (if not allowed)
        - remaining_tokens: dict
        - estimated_wait_time: int (if queued)
    """
    accounting_service = TokenAccountingService(db)
    
    # 1. Check workshop limits
    if not accounting_service.check_workshop_limits(workshop_id, estimated_tokens):
        return TokenValidationResult(
            is_allowed=False,
            reason="Workshop monthly token limit exceeded",
            remaining_tokens={"workshop": 0},
        )
    
    # 2. Check user daily limits
    if not accounting_service.check_user_limits(user_id, workshop_id, estimated_tokens):
        return TokenValidationResult(
            is_allowed=False,
            reason="User daily token limit exceeded",
            remaining_tokens=accounting_service.get_user_remaining_tokens(user_id, workshop_id),
        )
    
    # 3. Reserve tokens (optimistic locking)
    if not accounting_service.reserve_tokens(user_id, workshop_id, estimated_tokens):
        return TokenValidationResult(
            is_allowed=False,
            reason="Insufficient tokens available",
            remaining_tokens=accounting_service.get_user_remaining_tokens(user_id, workshop_id),
        )
    
    return TokenValidationResult(
        is_allowed=True,
        remaining_tokens=accounting_service.get_user_remaining_tokens(user_id, workshop_id),
    )
```

---

## 6. Queue System

### When Limits Reached

```python
class TokenQueue:
    """Queue system for requests when token limits are reached."""
    
    def enqueue_request(
        self,
        user_id: UUID,
        workshop_id: UUID,
        request_data: dict,
    ) -> QueueTicket:
        """Add request to queue."""
        
    def dequeue_request(self, ticket_id: str) -> dict | None:
        """Process queued request when tokens available."""
        
    def get_queue_position(self, ticket_id: str) -> int:
        """Get position in queue."""
        
    def estimate_wait_time(self, ticket_id: str) -> int:
        """Estimate wait time in seconds."""
```

**Implementation Options:**
- **Option A**: In-memory queue (Redis recommended)
- **Option B**: Database queue table
- **Option C**: Hybrid (Redis for active queue, DB for persistence)

**Recommended**: Redis for performance, DB for audit trail

---

## 7. Notification System

### Low Token Warnings

```python
class TokenNotificationService:
    """Sends notifications for token usage warnings."""
    
    TOKEN_WARNING_THRESHOLDS = {
        "workshop": {
            "critical": 0.10,  # 10% remaining
            "warning": 0.25,   # 25% remaining
        },
        "user": {
            "critical": 0.10,
            "warning": 0.25,
        },
    }
    
    def check_and_notify(self, user_id: UUID, workshop_id: UUID) -> None:
        """Check token levels and send notifications if needed."""
        
    def send_notification(
        self,
        user_id: UUID,
        notification_type: str,
        message: str,
    ) -> None:
        """Send notification (in-app, email, etc.)."""
```

### Notification Types

1. **Workshop Low Tokens** (to admins/owners)
   - "Workshop has 10% tokens remaining"
   - "Workshop monthly limit will reset on [date]"

2. **User Daily Limit Warning** (to user)
   - "You have used 80% of your daily limit"
   - "Daily limit resets at midnight"

3. **Workshop Limit Exceeded** (to admins/owners)
   - "Workshop monthly limit exceeded"
   - "Upgrade plan or wait for reset"

---

## 8. Integration Points

### Chat API Integration

```python
@router.post("/threads/{thread_id}/messages")
async def send_message(...):
    # 1. Estimate tokens needed
    estimated_tokens = estimate_tokens_for_request(content, context)
    
    # 2. Validate limits
    validation = await validate_token_limits(
        current_user.id,
        thread.workshop_id,
        estimated_tokens,
        db,
    )
    
    if not validation.is_allowed:
        # Option A: Return error immediately
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Token limit exceeded",
                "reason": validation.reason,
                "remaining": validation.remaining_tokens,
            }
        )
        
        # Option B: Queue request
        # ticket = token_queue.enqueue_request(...)
        # return {"status": "queued", "ticket_id": ticket.id}
    
    # 3. Proceed with AI call
    ai_response = await chat_provider.chat_completion(...)
    
    # 4. Record actual usage
    await record_token_usage(
        current_user.id,
        thread.workshop_id,
        ai_response.prompt_tokens,
        ai_response.completion_tokens,
        db,
    )
```

---

## 9. Token Reset Schedules

### Daily Reset (Midnight UTC)

```python
async def reset_daily_token_limits():
    """Reset daily token usage for all users."""
    # Run via cron: 0 0 * * * (daily at midnight)
    accounting_service = TokenAccountingService()
    accounting_service.reset_daily_limits()
```

### Monthly Reset (Workshop-specific)

```python
async def reset_monthly_token_limits():
    """Reset monthly token usage for workshops."""
    # Run via cron: 0 0 1 * * (first day of month)
    # Or per-workshop based on token_reset_date
    accounting_service = TokenAccountingService()
    accounting_service.reset_monthly_limits()
```

---

## 10. API Endpoints

### Token Management Endpoints

```python
@router.get("/workshops/{workshop_id}/tokens")
def get_workshop_tokens(...):
    """Get workshop token usage and limits."""

@router.get("/users/{user_id}/tokens")
def get_user_tokens(...):
    """Get user token usage and limits per workshop."""

@router.get("/tokens/remaining")
def get_remaining_tokens(...):
    """Get remaining tokens for current user in current workshop."""

@router.post("/tokens/validate")
async def validate_tokens(...):
    """Pre-validate token availability for estimated usage."""
```

---

## Summary

**Architecture**: Multi-level token accounting (workshop → user → role)
**Validation**: Pre-check before AI calls
**Queue System**: Redis-based queue for limit-exceeded requests
**Notifications**: Real-time warnings for low tokens
**Reset Schedules**: Daily (users) and monthly (workshops)

**Status**: Design Complete, Ready for Implementation

