"""File upload endpoints for chat attachments."""

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.config import settings
from app.models.user import User

router = APIRouter(prefix="/upload", tags=["upload"])

# Upload directory
UPLOAD_DIR = Path(settings.UPLOAD_DIR if hasattr(settings, "UPLOAD_DIR") else "uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Allowed file types
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_DOCUMENT_TYPES = {"application/pdf", "text/plain"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_DOCUMENT_TYPES

# Max file size (10MB)
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/chat-attachment")
async def upload_chat_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a file attachment for chat messages."""
    # Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_TYPES)}",
        )

    # Read file content to check size
    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE / 1024 / 1024}MB",
        )

    # Generate unique filename
    file_ext = Path(file.filename).suffix if file.filename else ".bin"
    file_id = str(uuid.uuid4())
    filename = f"{file_id}{file_ext}"
    file_path = UPLOAD_DIR / filename

    # Save file
    with open(file_path, "wb") as f:
        f.write(content)

    # Return file info
    return {
        "file_id": file_id,
        "filename": file.filename,
        "file_path": str(file_path.relative_to(Path.cwd())),
        "file_url": f"/api/v1/upload/files/{filename}",
        "file_size": len(content),
        "content_type": file.content_type,
        "is_image": file.content_type in ALLOWED_IMAGE_TYPES,
    }


@router.get("/files/{filename}")
async def get_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Serve uploaded files."""
    file_path = UPLOAD_DIR / filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    return FileResponse(
        file_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@router.delete("/files/{filename}")
async def delete_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an uploaded file."""
    file_path = UPLOAD_DIR / filename

    if not file_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found",
        )

    file_path.unlink()

    return {"message": "File deleted successfully"}

