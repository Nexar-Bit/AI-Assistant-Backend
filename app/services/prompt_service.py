"""Service for managing AI prompts (global and workshop-specific)."""

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.models.prompt import GlobalPrompt
from app.workshops.models import Workshop

logger = logging.getLogger("app.services.prompt")


def get_global_prompt(db: Session) -> Optional[str]:
    """Get the active global prompt (platform admin only)."""
    prompt = db.query(GlobalPrompt).filter(
        GlobalPrompt.is_active == True,
        GlobalPrompt.is_deleted == False
    ).order_by(GlobalPrompt.created_at.desc()).first()
    
    if prompt:
        return prompt.prompt_text
    return None


def get_workshop_prompt(db: Session, workshop_id) -> Optional[str]:
    """Get the workshop-specific prompt."""
    import uuid
    if isinstance(workshop_id, str):
        try:
            workshop_id = uuid.UUID(workshop_id)
        except ValueError:
            return None
    
    workshop = db.query(Workshop).filter(Workshop.id == workshop_id).first()
    if workshop and workshop.workshop_prompt:
        return workshop.workshop_prompt
    return None


def build_system_prompt(
    db: Session,
    workshop_id,
    vehicle_context: Optional[str] = None,
    error_codes: Optional[str] = None,
    vehicle_km: Optional[int] = None
) -> str:
    """
    Build the complete system prompt by combining:
    1. Global prompt (if exists)
    2. Workshop prompt (if exists)
    3. Default prompt (if no custom prompts)
    4. Vehicle context, error codes, and KM
    """
    # Default prompt
    default_prompt = (
        "You are an expert automotive diagnostic assistant for professional technicians. "
        "Provide clear, concise, and actionable diagnostic steps and repair advice. "
        "Always prioritize safety and best practices. "
        "If specific vehicle details are provided, use them to tailor your response."
    )
    
    # Get global prompt
    global_prompt = get_global_prompt(db)
    
    # Get workshop prompt
    workshop_prompt = get_workshop_prompt(db, workshop_id)
    
    # Build the base prompt
    if global_prompt:
        base_prompt = global_prompt
        if workshop_prompt:
            # Combine: global + workshop (workshop can override/extend)
            base_prompt = f"{global_prompt}\n\n--- Workshop-Specific Instructions ---\n{workshop_prompt}"
    elif workshop_prompt:
        base_prompt = workshop_prompt
    else:
        base_prompt = default_prompt
    
    # Add vehicle context
    context_parts = []
    if vehicle_context:
        context_parts.append(f"Vehicle Context:\n{vehicle_context}")
    if error_codes:
        context_parts.append(f"Reported Error Codes (DTCs): {error_codes}")
    if vehicle_km is not None:
        context_parts.append(f"Current Odometer: {vehicle_km} KM")
    
    if context_parts:
        base_prompt += "\n\n" + "\n\n".join(context_parts)
    
    return base_prompt

