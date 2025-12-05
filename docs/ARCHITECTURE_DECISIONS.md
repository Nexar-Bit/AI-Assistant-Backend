# Multi-Tenant Architecture Decisions

## Decision Summary

**Date**: 2025-01-XX  
**Status**: ✅ Approved and Implemented

---

## 1. Database Strategy: **Option A - Single Database with `workshop_id`**

### Decision
✅ **Chosen: Single database with tenant ID (`workshop_id`) on all tenant-scoped tables**

### Rationale
- **MVP Timeline**: 2-week deadline requires rapid development
- **Operational Simplicity**: Single database is easier to backup, monitor, and maintain
- **Cost Efficiency**: No need for multiple database instances
- **Cross-Tenant Analytics**: Platform admins can analyze aggregate data
- **Scalability Path**: Can migrate to Option B or C later if needed (100+ workshops)

### Trade-offs Accepted
- Requires strict query filtering (mitigated by middleware/dependencies)
- Potential for data leakage if queries miss `workshop_id` (mitigated by database constraints and code review)

### Implementation
- All tenant-scoped tables have `workshop_id` foreign key
- Database constraints enforce referential integrity
- Application-level dependencies enforce membership checks
- Query patterns documented and enforced

---

## 2. Data Isolation Level: **Complete Isolation with Shared Knowledge Base**

### Decision
✅ **Chosen: Complete data isolation per workshop, with optional shared knowledge base**

### Isolated Data (per workshop)
- ✅ Chat threads and messages
- ✅ Vehicle records (even if same license plate)
- ✅ User memberships and roles
- ✅ Token usage and limits
- ✅ Workshop settings and branding

### Shared Data (across workshops)
- ✅ Vehicle knowledge base (makes, models, common issues) - Future enhancement
- ✅ AI model configurations
- ✅ System-wide audit logs (for platform admins)

### Hybrid Approach
- Vehicles are **workshop-scoped** by default (`workshop_id` on Vehicle model)
- Same license plate can exist in multiple workshops (different physical vehicles)
- Future: Optional "shared vehicle registry" for common makes/models lookup

---

## 3. Workshop Hierarchy

```
Workshop (Tenant)
  ├── Owner (1 user) - Full control
  ├── Admins (multiple) - Manage workshop, users, settings
  ├── Technicians (multiple) - Create threads, manage vehicles
  ├── Viewers (multiple) - Read-only access
  │
  ├── Vehicles (workshop-scoped)
  │   ├── License Plate (unique within workshop)
  │   ├── Make/Model/Year
  │   ├── Current KM
  │   ├── Error Codes (DTC)
  │   └── Service History
  │
  └── Chat Threads
      ├── Vehicle Context (KM, error codes)
      ├── Messages (user + assistant)
      └── Token Usage (aggregated per thread)
```

---

## 4. Isolation Enforcement (Multi-Layer Defense)

### Layer 1: Database Constraints ✅
- Foreign keys with `ON DELETE CASCADE` for workshop-scoped tables
- Unique constraints within workshop scope (e.g., `(workshop_id, license_plate)`)
- Indexes for performance on `workshop_id` filters

### Layer 2: Application Dependencies ✅
- `require_workshop_membership()` FastAPI dependency
- Enforces user membership and role hierarchy
- Used in all workshop-scoped endpoints

### Layer 3: Query Patterns ✅
- All queries filter by `workshop_id`
- Base query helpers enforce workshop scope
- Code review checklist includes isolation checks

### Layer 4: Future: Row-Level Security (RLS)
- PostgreSQL RLS policies for defense-in-depth
- Can be added if compliance requirements demand it

---

## 5. Security Model

### Access Control Matrix

| Role | View Own Data | View Workshop Data | Manage Workshop | Manage Users | Token Limits |
|------|---------------|-------------------|-----------------|-------------|-------------|
| Owner | ✅ | ✅ | ✅ | ✅ | Workshop limit |
| Admin | ✅ | ✅ | ✅ | ✅ | Workshop limit |
| Technician | ✅ | ✅ | ❌ | ❌ | Personal limit |
| Viewer | ✅ | ✅ (read-only) | ❌ | ❌ | No AI access |

### Query Injection Prevention
- ✅ All queries use SQLAlchemy ORM (parameterized queries)
- ✅ No raw SQL in application code
- ✅ Workshop ID from authenticated user context (never from user input directly)

---

## 6. Migration Path (Future Scaling)

### Option B: Separate Database per Workshop
**When**: 100+ workshops, compliance requirements, or per-tenant scaling needs

**Migration Steps**:
1. Export workshop data to new database
2. Update connection strings per tenant
3. Application changes to route to correct database

**Pros**: Complete isolation, easier per-tenant scaling  
**Cons**: Complex to manage, harder cross-tenant analytics

### Option C: Schema Isolation
**When**: Need better isolation than Option A, but want shared infrastructure

**Migration Steps**:
1. Create schema per workshop: `workshop_abc123`
2. Move tables to schemas
3. Update `search_path` per connection

**Pros**: Good isolation, can still query across if needed  
**Cons**: PostgreSQL schema management complexity

**Current Recommendation**: Stay with Option A until 100+ workshops or specific compliance requirements.

---

## 7. Implementation Status

### ✅ Completed
- [x] Database models with `workshop_id` isolation
- [x] Alembic migration with constraints and indexes
- [x] `require_workshop_membership()` dependency
- [x] Workshop CRUD API endpoints
- [x] Chat API with workshop isolation
- [x] Documentation and architecture decisions

### 🚧 In Progress
- [ ] Frontend workshop selector/switcher
- [ ] Chat UI components
- [ ] Vehicle context form (KM, error codes)
- [ ] Token usage dashboard per workshop

### 📋 Future Enhancements
- [ ] Row-Level Security (RLS) policies
- [ ] Shared vehicle knowledge base
- [ ] Cross-workshop analytics (admin only)
- [ ] Workshop-level audit logs

---

## 8. Testing Strategy

### Isolation Tests
```python
def test_workshop_isolation():
    """Ensure Workshop A cannot access Workshop B's data."""
    workshop_a = create_workshop(name="Shop A")
    workshop_b = create_workshop(name="Shop B")
    
    thread_a = create_chat_thread(workshop_id=workshop_a.id)
    
    # Attempt to access from Workshop B context
    with pytest.raises(HTTPException):
        get_thread(thread_id=thread_a.id, workshop_id=workshop_b.id)
```

### Query Auditing
- Log all queries missing `workshop_id` filter
- Alert on cross-workshop data access attempts
- Regular security audits

---

## 9. Code Examples

### ✅ CORRECT: Workshop-Scoped Query
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

### ❌ WRONG: Missing Workshop Filter
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
**Enforcement**: Multi-layer (constraints + dependencies + patterns)  
**Scalability**: Can migrate to separate databases/schemas if needed  
**Security**: Defense-in-depth approach  

**Status**: ✅ Design Complete, Implementation In Progress

