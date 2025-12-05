# Multi-Tenant Architecture Design

## Executive Summary

**Chosen Strategy: Option A - Single Database with `workshop_id` Isolation**

This document outlines the multi-tenant architecture for the Vehicle Diagnostics AI Platform, ensuring complete data isolation between workshops while maintaining operational simplicity for MVP delivery.

---

## 1. Database Strategy Decision

### ✅ **Selected: Single Database with Tenant ID (workshop_id)**

**Rationale:**
- **MVP Timeline**: 2-week deadline requires rapid development
- **Operational Simplicity**: Single database is easier to backup, monitor, and maintain
- **Cost Efficiency**: No need for multiple database instances
- **Cross-Tenant Analytics**: Platform admins can analyze aggregate data
- **Scalability Path**: Can migrate to Option B or C later if needed

**Trade-offs:**
- Requires strict query filtering (mitigated by middleware/dependencies)
- Potential for data leakage if queries miss `workshop_id` (mitigated by database constraints and code review)

---

## 2. Data Isolation Level

### **Complete Isolation with Shared Knowledge Base**

**Isolated Data (per workshop):**
- ✅ Chat threads and messages
- ✅ Vehicle records (even if same license plate)
- ✅ User memberships and roles
- ✅ Token usage and limits
- ✅ Workshop settings and branding

**Shared Data (across workshops):**
- ✅ Vehicle knowledge base (makes, models, common issues) - Future enhancement
- ✅ AI model configurations
- ✅ System-wide audit logs (for platform admins)

**Hybrid Approach:**
- Vehicles are **workshop-scoped** by default (`workshop_id` on Vehicle model)
- Same license plate can exist in multiple workshops (different physical vehicles)
- Future: Optional "shared vehicle registry" for common makes/models lookup

---

## 3. Workshop Hierarchy

```
Workshop (Tenant)
  ├── Owner (1 user)
  ├── Admins (multiple users)
  ├── Technicians (multiple users)
  ├── Viewers (multiple users)
  │
  ├── Vehicles (workshop-scoped)
  │   ├── License Plate
  │   ├── Make/Model/Year
  │   ├── Current KM
  │   └── Error Codes
  │
  └── Chat Threads
      ├── Vehicle Context (KM, error codes)
      ├── Messages (user + assistant)
      └── Token Usage (aggregated)
```

---

## 4. Isolation Enforcement Strategy

### **Layer 1: Database Constraints**

```sql
-- All tenant-scoped tables MUST have workshop_id
ALTER TABLE chat_threads 
  ADD CONSTRAINT fk_chat_threads_workshop 
  FOREIGN KEY (workshop_id) REFERENCES workshops(id) ON DELETE CASCADE;

-- Unique constraints within workshop scope
CREATE UNIQUE INDEX idx_vehicles_workshop_license 
  ON vehicles(workshop_id, license_plate) 
  WHERE is_deleted = false;
```

### **Layer 2: Application-Level Dependencies**

```python
# FastAPI dependency to enforce workshop context
def require_workshop_membership(
    workshop_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WorkshopMember:
    """Ensures user is a member of the workshop."""
    membership = db.query(WorkshopMember).filter(
        WorkshopMember.workshop_id == workshop_id,
        WorkshopMember.user_id == current_user.id,
        WorkshopMember.is_active == True,
    ).first()
    
    if not membership:
        raise HTTPException(403, "Not a member of this workshop")
    
    return membership
```

### **Layer 3: Query Filtering Middleware**

```python
# Base query filter for all workshop-scoped queries
def get_workshop_scope_query(
    model: Type[Base],
    workshop_id: UUID,
    db: Session,
):
    """Returns query filtered by workshop_id."""
    return db.query(model).filter(
        model.workshop_id == workshop_id,
        model.is_deleted == False,
    )
```

### **Layer 4: Row-Level Security (Future Enhancement)**

PostgreSQL Row-Level Security (RLS) policies can be added for defense-in-depth:

```sql
ALTER TABLE chat_threads ENABLE ROW LEVEL SECURITY;

CREATE POLICY workshop_isolation ON chat_threads
  FOR ALL
  USING (workshop_id = current_setting('app.current_workshop_id')::UUID);
```

---

## 5. Data Model Isolation Points

### **Workshop-Scoped Tables**

| Table | Isolation Field | Notes |
|-------|----------------|-------|
| `workshops` | `id` (primary) | Root tenant entity |
| `workshop_members` | `workshop_id` | User-workshop relationships |
| `chat_threads` | `workshop_id` | **CRITICAL**: All queries must filter |
| `chat_messages` | Via `thread_id` → `workshop_id` | Indirect, but enforced |
| `vehicles` | `workshop_id` | Same license plate can exist in multiple workshops |
| `consultation_pdfs` | Via `consultation_id` → `workshop_id` | Legacy table |

### **User-Scoped Tables (Cross-Workshop)**

| Table | Scope | Notes |
|-------|-------|-------|
| `users` | Global | Users can belong to multiple workshops |
| `audit_logs` | Global | Platform-wide audit trail |

---

## 6. Security Considerations

### **Query Injection Prevention**

✅ **All queries use SQLAlchemy ORM** (parameterized queries)
✅ **No raw SQL** in application code
✅ **Workshop ID from authenticated user context** (never from user input directly)

### **Access Control Matrix**

| Role | View Own Data | View Workshop Data | Manage Workshop | Manage Users |
|------|---------------|-------------------|-----------------|-------------|
| Owner | ✅ | ✅ | ✅ | ✅ |
| Admin | ✅ | ✅ | ✅ | ✅ |
| Technician | ✅ | ✅ | ❌ | ❌ |
| Viewer | ✅ | ✅ (read-only) | ❌ | ❌ |

---

## 7. Migration Path (Future)

If scaling requires it, migration options:

1. **Option B (Separate Databases)**: 
   - Export workshop data to new database
   - Update connection strings per tenant
   - Requires application changes

2. **Option C (Schema Isolation)**:
   - Create schema per workshop: `workshop_abc123`
   - Move tables to schemas
   - Update search_path per connection

**Current Recommendation**: Stay with Option A until 100+ workshops or specific compliance requirements.

---

## 8. Testing Strategy

### **Isolation Tests**

```python
def test_workshop_isolation():
    """Ensure Workshop A cannot access Workshop B's data."""
    # Create two workshops
    workshop_a = create_workshop(name="Shop A")
    workshop_b = create_workshop(name="Shop B")
    
    # Create thread in Workshop A
    thread_a = create_chat_thread(workshop_id=workshop_a.id)
    
    # Attempt to access from Workshop B context
    with pytest.raises(HTTPException):
        get_thread(thread_id=thread_a.id, workshop_id=workshop_b.id)
```

### **Query Auditing**

- Log all queries missing `workshop_id` filter
- Alert on cross-workshop data access attempts
- Regular security audits

---

## 9. Implementation Checklist

- [x] Add `workshop_id` to all tenant-scoped models
- [x] Create `WorkshopMember` model for access control
- [x] Implement `require_workshop_membership` dependency
- [ ] Add database constraints (FK + unique indexes)
- [ ] Create isolation test suite
- [ ] Document query patterns in codebase
- [ ] Add query auditing middleware
- [ ] Implement workshop switching UI
- [ ] Add token limits per workshop

---

## 10. Code Examples

### **✅ CORRECT: Workshop-Scoped Query**

```python
@router.get("/threads")
def list_threads(
    workshop_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    membership: WorkshopMember = Depends(require_workshop_membership(workshop_id)),
):
    # ✅ Correct: Filter by workshop_id
    threads = db.query(ChatThread).filter(
        ChatThread.workshop_id == workshop_id,  # CRITICAL
        ChatThread.user_id == current_user.id,
    ).all()
    return threads
```

### **❌ WRONG: Missing Workshop Filter**

```python
# ❌ NEVER DO THIS - Missing workshop_id filter
threads = db.query(ChatThread).filter(
    ChatThread.user_id == current_user.id,  # Missing workshop_id!
).all()
```

---

## Summary

**Architecture**: Single database with `workshop_id` isolation
**Isolation Level**: Complete data isolation per workshop
**Enforcement**: Database constraints + application dependencies + query patterns
**Scalability**: Can migrate to separate databases/schemas if needed
**Security**: Multi-layer defense (constraints, dependencies, middleware)

**Status**: ✅ Design Complete, Implementation In Progress

