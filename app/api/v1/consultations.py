from base64 import b64decode, b64encode
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, WebSocket, WebSocketDisconnect
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models.consultation import Consultation
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.ai_service import AIRequest
from app.services.openai_service import OpenAIProvider
from app.services.token_service import ensure_within_daily_limit


router = APIRouter(prefix="/consultations", tags=["consultations"])

active_websockets: set[WebSocket] = set()


def get_ai_provider() -> OpenAIProvider:
    # In the future we can branch on settings to use LocalAIProvider
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key is not configured. Please set OPENAI_API_KEY in your environment variables.",
        )
    return OpenAIProvider(api_key=api_key, default_model="gpt-4o-mini")


def _encode_cursor(created_at, id_) -> str:
    raw = f"{created_at.isoformat()}|{id_}"
    return b64encode(raw.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    raw = b64decode(cursor.encode("utf-8")).decode("utf-8")
    created_str, id_str = raw.split("|", 1)
    return created_str, id_str


@router.get("/")
def list_consultations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    license_plate: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    q: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
):
    """List consultations with filtering and cursor-based pagination."""
    limit = min(max(limit, 1), 100)

    query = (
        db.query(Consultation)
        .filter(Consultation.user_id == current_user.id)
    )

    if license_plate:
        query = query.filter(Consultation.license_plate.ilike(f"%{license_plate}%"))
    if is_resolved is not None:
        query = query.filter(Consultation.is_resolved.is_(is_resolved))
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                Consultation.query.ilike(like),
                Consultation.ai_response.ilike(like),
            )
        )

    if start_date:
        query = query.filter(Consultation.created_at >= start_date)
    if end_date:
        query = query.filter(Consultation.created_at <= end_date)

    query = query.order_by(Consultation.created_at.desc(), Consultation.id.desc())

    if cursor:
        created_str, id_str = _decode_cursor(cursor)
        # PostgreSQL can compare timestamp and UUID lexicographically with pair condition
        query = query.filter(
            or_(
                Consultation.created_at < created_str,
                and_(
                    Consultation.created_at == created_str,
                    Consultation.id < id_str,
                ),
            )
        )

    items = query.limit(limit + 1).all()
    next_cursor: Optional[str] = None
    if len(items) > limit:
        last = items[limit - 1]
        next_cursor = _encode_cursor(last.created_at, last.id)
        items = items[:limit]

    return {"items": items, "next_cursor": next_cursor}


@router.get("/{consultation_id}")
def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consultation = (
        db.query(Consultation)
        .filter(
            Consultation.id == consultation_id,
            Consultation.user_id == current_user.id,
        )
        .first()
    )
    if not consultation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return consultation


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_consultation(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    license_plate = payload.get("license_plate")
    query_text = payload.get("query")
    if not license_plate or not query_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="license_plate and query are required",
        )

    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.license_plate == license_plate)
        .first()
    )

    vehicle_context = (
        f"License plate: {license_plate}\n"
        f"Make: {vehicle.make if vehicle else 'Unknown'}\n"
        f"Model: {vehicle.model if vehicle else 'Unknown'}\n"
        f"Year: {vehicle.year if vehicle else 'Unknown'}\n"
        f"VIN: {vehicle.vin if vehicle else 'Unknown'}"
    )

    # Get AI provider (with error handling)
    try:
        provider = get_ai_provider()
    except HTTPException:
        raise
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"AI service is not available: {str(e)}. Please install required packages: pip install openai tiktoken tenacity",
        )

    ai_request = AIRequest(
        user_id=str(current_user.id),
        vehicle_context=vehicle_context,
        query=query_text,
        model=payload.get("model") or "gpt-4o-mini",
        temperature=float(payload.get("temperature", 0.1)),
        max_tokens=int(payload.get("max_tokens", 800)),
    )

    # run AI and enforce token limits
    ai_response = await provider.run_diagnostics(ai_request)
    ensure_within_daily_limit(db, current_user, ai_response.total_tokens)

    consultation = Consultation(
        user_id=current_user.id,
        vehicle_id=vehicle.id if vehicle else None,
        license_plate=license_plate,
        query=query_text,
        ai_response=ai_response.content,
        ai_model_used=ai_response.model,
        prompt_tokens=ai_response.prompt_tokens,
        completion_tokens=ai_response.completion_tokens,
        total_tokens=ai_response.total_tokens,
        estimated_cost=ai_response.estimated_cost,
        is_resolved=False,
        metadata={},
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    # push basic status update to websocket clients
    await _broadcast_update(
        {
            "event": "consultation_created",
            "id": str(consultation.id),
            "license_plate": consultation.license_plate,
        }
    )

    return consultation


@router.put("/{consultation_id}")
async def update_consultation(
    consultation_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update consultation with optimistic concurrency using integer version."""
    expected_version: Optional[int] = payload.get("version")
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="version is required for update",
        )

    consultation: Optional[Consultation] = (
        db.query(Consultation)
        .filter(
            Consultation.id == consultation_id,
            Consultation.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )
    if not consultation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    if consultation.version != expected_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Consultation has been modified by another process",
        )

    # allow updating resolution status and notes
    if "is_resolved" in payload:
        consultation.is_resolved = bool(payload["is_resolved"])
    if "resolution_notes" in payload:
        consultation.resolution_notes = payload["resolution_notes"]

    consultation.version += 1

    db.add(consultation)
    db.commit()
    db.refresh(consultation)

    await _broadcast_update(
        {
            "event": "consultation_updated",
            "id": str(consultation.id),
            "is_resolved": consultation.is_resolved,
        }
    )

    return consultation


@router.delete("/{consultation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    consultation: Optional[Consultation] = (
        db.query(Consultation)
        .filter(
            Consultation.id == consultation_id,
            Consultation.user_id == current_user.id,
        )
        .first()
    )
    if not consultation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    db.delete(consultation)
    db.commit()

    await _broadcast_update(
        {
            "event": "consultation_deleted",
            "id": consultation_id,
        }
    )

    return None


@router.websocket("/ws")
async def consultations_ws(websocket: WebSocket):
    """Simple websocket for real-time consultation status events."""
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        while True:
            # We don't expect messages from client; keep connection alive.
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.discard(websocket)


async def _broadcast_update(message: dict[str, Any]) -> None:
    if not active_websockets:
        return
    dead: set[WebSocket] = set()
    for ws in active_websockets:
        try:
            await ws.send_json(message)
        except Exception:
            dead.add(ws)
    for ws in dead:
        active_websockets.discard(ws)


