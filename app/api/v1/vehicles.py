import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.models.vehicle import Vehicle


router = APIRouter(prefix="/vehicles", tags=["vehicles"])


def _validate_license_plate(plate: str) -> str:
    plate = plate.upper().strip()
    if not plate or len(plate) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid license plate format",
        )
    return plate


@router.get("/")
def list_vehicles(
    license_plate: str | None = None,
    workshop_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List vehicles with optional filters."""
    query = db.query(Vehicle)
    
    # Filter by user's vehicles or workshop
    if workshop_id:
        query = query.filter(Vehicle.workshop_id == workshop_id)
    else:
        query = query.filter(Vehicle.created_by_user_id == current_user.id)
    
    # Filter by license plate (search)
    if license_plate:
        plate = license_plate.upper().strip()
        query = query.filter(Vehicle.license_plate.ilike(f"%{plate}%"))
    
    vehicles = query.order_by(Vehicle.created_at.desc()).all()
    return vehicles


@router.post("/", status_code=status.HTTP_201_CREATED)
def register_vehicle(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a vehicle (requires technician or higher role)."""
    from app.api.v1 import workshops
    
    workshop_id = payload.get("workshop_id")
    if not workshop_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="workshop_id is required",
        )
    
    try:
        workshop_uuid = uuid.UUID(workshop_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid workshop_id",
        )
    
    # Require technician or higher role to create vehicles
    workshops._ensure_workshop_member(db, current_user.id, workshop_uuid, min_role="technician")
    
    plate = _validate_license_plate(payload.get("license_plate", ""))

    existing = db.query(Vehicle).filter(Vehicle.license_plate == plate).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vehicle with this license plate already exists",
        )

    vehicle = Vehicle(
        license_plate=plate,
        vehicle_type=payload.get("vehicle_type"),
        make=payload.get("make"),
        model=payload.get("model"),
        year=payload.get("year"),
        vin=payload.get("vin"),
        current_km=payload.get("current_km"),
        engine_type=payload.get("engine_type"),
        fuel_type=payload.get("fuel_type"),
        workshop_id=payload.get("workshop_id"),
        created_by_user_id=current_user.id,
    )
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.get("/validate")
def validate_vehicle(
    license_plate: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    plate = _validate_license_plate(license_plate)
    vehicle = db.query(Vehicle).filter(Vehicle.license_plate == plate).first()
    return {"exists": bool(vehicle), "license_plate": plate}


@router.get("/{vehicle_id}")
def get_vehicle(
    vehicle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    return vehicle


@router.put("/{vehicle_id}")
def update_vehicle(
    vehicle_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a vehicle (requires technician or higher role)."""
    from app.api.v1 import workshops
    
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    
    # Require technician or higher role to update vehicles
    if vehicle.workshop_id:
        workshops._ensure_workshop_member(db, current_user.id, vehicle.workshop_id, min_role="technician")

    if "license_plate" in payload:
        plate = _validate_license_plate(payload["license_plate"])
        conflict = (
            db.query(Vehicle)
            .filter(Vehicle.license_plate == plate, Vehicle.id != vehicle_id)
            .first()
        )
        if conflict:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Vehicle with this license plate already exists",
            )
        vehicle.license_plate = plate

    for field in ("vehicle_type", "make", "model", "year", "vin", "current_km", "engine_type", "fuel_type", "workshop_id"):
        if field in payload:
            setattr(vehicle, field, payload[field])

    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)
    return vehicle


@router.delete("/{vehicle_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vehicle(
    vehicle_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a vehicle (requires technician or higher role)."""
    from app.api.v1 import workshops
    
    vehicle = (
        db.query(Vehicle)
        .filter(
            Vehicle.id == vehicle_id,
            Vehicle.created_by_user_id == current_user.id,
        )
        .first()
    )
    if not vehicle:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    # Require technician or higher role to delete vehicles
    if vehicle.workshop_id:
        workshops._ensure_workshop_member(db, current_user.id, vehicle.workshop_id, min_role="technician")

    db.delete(vehicle)
    db.commit()
    return None


