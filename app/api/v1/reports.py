from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.consultation import Consultation
from app.models.consultation_pdf import ConsultationPDF
from app.models.user import User
from app.models.vehicle import Vehicle
from app.services.audit_service import log_auth_event
from app.services.pdf_service import generate_consultation_pdf


router = APIRouter(prefix="/reports", tags=["reports"])


@router.post("/consultations/{consultation_id}", status_code=status.HTTP_201_CREATED)
def generate_report_for_consultation(
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

    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.license_plate == consultation.license_plate)
        .first()
    )
    pdf = generate_consultation_pdf(
        db,
        consultation=consultation,
        user=current_user,
        vehicle=vehicle,
    )
    return pdf


@router.post("/consultations/batch", status_code=status.HTTP_201_CREATED)
def generate_reports_batch(
    ids: List[str],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pdfs = []
    for cid in ids:
        consultation = (
            db.query(Consultation)
            .filter(
                Consultation.id == cid,
                Consultation.user_id == current_user.id,
            )
            .first()
        )
        if not consultation:
            continue
        vehicle = (
            db.query(Vehicle)
            .filter(Vehicle.license_plate == consultation.license_plate)
            .first()
        )
        pdf = generate_consultation_pdf(
            db,
            consultation=consultation,
            user=current_user,
            vehicle=vehicle,
        )
        pdfs.append(pdf)
    return pdfs


@router.get("/consultations/{consultation_id}/download")
def download_report_for_consultation(
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

    vehicle = (
        db.query(Vehicle)
        .filter(Vehicle.license_plate == consultation.license_plate)
        .first()
    )
    pdf = generate_consultation_pdf(
        db,
        consultation=consultation,
        user=current_user,
        vehicle=vehicle,
    )

    pdf.download_count += 1
    db.add(pdf)
    db.commit()

    # simple analytics via audit log (resource_type=report)
    log_auth_event(
        db,
        user_id=str(current_user.id),
        action_type="REPORT_DOWNLOAD",
        success=True,
        ip_address=None,
        user_agent=None,
        details={"consultation_id": consultation_id},
    )

    return FileResponse(
        path=pdf.file_path,
        filename=f"consultation-{consultation.license_plate}.pdf",
        media_type="application/pdf",
    )


@router.get("/stats")
def report_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Basic analytics: total downloads and count per day."""
    query = db.query(
        func.date(ConsultationPDF.created_at).label("day"),
        func.count(ConsultationPDF.id).label("reports"),
        func.coalesce(func.sum(ConsultationPDF.download_count), 0).label(
            "downloads"
        ),
    )

    if start_date:
        query = query.filter(ConsultationPDF.created_at >= start_date)
    if end_date:
        query = query.filter(ConsultationPDF.created_at <= end_date)

    query = query.group_by(func.date(ConsultationPDF.created_at)).order_by(
        func.date(ConsultationPDF.created_at)
    )

    rows = query.all()
    return [
        {"day": str(r.day), "reports": int(r.reports), "downloads": int(r.downloads)}
        for r in rows
    ]
