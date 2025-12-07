from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

import uuid

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.models.consultation import Consultation
from app.models.consultation_pdf import ConsultationPDF
from app.models.chat_thread_pdf import ChatThreadPDF
from app.models.user import User
from app.models.vehicle import Vehicle
from app.chat.models import ChatThread, ChatMessage
from app.chat.messages import MessageHandler
from app.chat.sessions import ChatSessionManager
from app.services.audit_service import log_auth_event
from app.services.pdf_service import generate_consultation_pdf, generate_chat_thread_pdf


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


@router.post("/chat-threads/{thread_id}", status_code=status.HTTP_201_CREATED)
def generate_report_for_chat_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate PDF for a chat thread."""
    try:
        thread_uuid = uuid.UUID(thread_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thread_id",
        )
    
    # Get thread using ChatSessionManager to ensure user has access
    thread = ChatSessionManager.get_session(db, thread_uuid, current_user.id)
    if not thread:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Thread not found",
        )
    
    # Get all messages
    messages = MessageHandler.get_thread_messages(db, thread_uuid)
    
    # Get vehicle if available
    vehicle = None
    if thread.vehicle_id:
        vehicle = db.query(Vehicle).filter(Vehicle.id == thread.vehicle_id).first()
    
    # Generate PDF
    pdf = generate_chat_thread_pdf(
        db,
        thread=thread,
        messages=messages,
        user=current_user,
        vehicle=vehicle,
    )
    return pdf


@router.get("/chat-threads/{thread_id}/download")
def download_report_for_chat_thread(
    thread_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download PDF for a chat thread."""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        thread_uuid = uuid.UUID(thread_id)
    except ValueError as e:
        logger.error(f"Invalid thread_id format: {thread_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid thread_id",
        )
    
    try:
        # Get thread using ChatSessionManager to ensure user has access
        thread = ChatSessionManager.get_session(db, thread_uuid, current_user.id)
        if not thread:
            logger.warning(f"Thread not found: {thread_id} for user {current_user.id}")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Thread not found",
            )
        
        # Get all messages
        messages = MessageHandler.get_thread_messages(db, thread_uuid)
        logger.info(f"Retrieved {len(messages)} messages for thread {thread_id}")
        
        # Get vehicle if available
        vehicle = None
        if thread.vehicle_id:
            vehicle = db.query(Vehicle).filter(Vehicle.id == thread.vehicle_id).first()
        
        # Generate PDF
        try:
            pdf = generate_chat_thread_pdf(
                db,
                thread=thread,
                messages=messages,
                user=current_user,
                vehicle=vehicle,
            )
            logger.info(f"PDF generated successfully: {pdf.file_path}")
        except Exception as e:
            logger.error(f"Error generating PDF for thread {thread_id}: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to generate PDF: {str(e)}",
            )
        
        # Increment download count
        pdf.download_count += 1
        db.add(pdf)
        db.commit()
        
        # Log download event
        log_auth_event(
            db,
            user_id=str(current_user.id),
            action_type="REPORT_DOWNLOAD",
            success=True,
            ip_address=None,
            user_agent=None,
            details={"thread_id": thread_id, "type": "chat_thread"},
        )
        
        # Generate filename
        date_str = thread.created_at.strftime("%Y%m%d") if thread.created_at else ""
        filename = f"diagnostic-report-{thread.license_plate}-{date_str}.pdf"
        
        # Verify file exists before returning
        import os
        if not os.path.exists(pdf.file_path):
            logger.error(f"PDF file not found at path: {pdf.file_path}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="PDF file not found",
            )
        
        return FileResponse(
            path=pdf.file_path,
            filename=filename,
            media_type="application/pdf",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error downloading PDF for thread {thread_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        )
