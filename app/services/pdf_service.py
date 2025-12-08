from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

try:  # optional so global Python can run without weasyprint
    from weasyprint import HTML, CSS  # type: ignore
except ImportError:  # pragma: no cover - fallback
    HTML = None  # type: ignore[assignment]
    CSS = None  # type: ignore[assignment]

from app.core.config import settings
from app.models.consultation import Consultation
from app.models.consultation_pdf import ConsultationPDF
from app.models.user import User
from app.models.vehicle import Vehicle
from app.chat.models import ChatThread, ChatMessage
from app.models.chat_thread_pdf import ChatThreadPDF


BRAND_PRIMARY_COLOR = "#0ea5e9"  # sky-500


def _ensure_output_dir() -> Path:
  """Ensure PDF output directory exists and is writable."""
  import logging
  logger = logging.getLogger(__name__)
  
  # Use absolute path to avoid issues with relative paths
  # On Render, use /tmp for writable directory
  pdf_dir = settings.PDF_OUTPUT_DIR
  if not os.path.isabs(pdf_dir):
    if os.path.exists("/tmp"):
      # Render or Linux system - use /tmp
      pdf_dir = f"/tmp/{pdf_dir}"
    else:
      # Local development - use project root
      pdf_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), pdf_dir)
  
  out = Path(pdf_dir)
  try:
    out.mkdir(parents=True, exist_ok=True)
    # Test write permissions
    test_file = out / ".test_write"
    test_file.touch()
    test_file.unlink()
    logger.info(f"PDF output directory ready: {out.absolute()}")
  except PermissionError as e:
    logger.error(f"Permission denied creating PDF output directory {out}: {e}", exc_info=True)
    raise RuntimeError(f"Cannot create PDF output directory (permission denied): {out}")
  except OSError as e:
    logger.error(f"OS error creating PDF output directory {out}: {e}", exc_info=True)
    raise RuntimeError(f"Cannot create PDF output directory: {e}")
  except Exception as e:
    logger.error(f"Failed to create/access PDF output directory {out}: {e}", exc_info=True)
    raise RuntimeError(f"Cannot access PDF output directory: {e}")
  return out


def _build_html(consultation: Consultation, user: User | None, vehicle: Vehicle | None) -> str:
  """Build HTML for consultation report with simple company branding."""
  tech_name = getattr(user, "username", "Technician")
  header_vehicle = (
      f"{vehicle.make or ''} {vehicle.model or ''} {vehicle.year or ''}".strip()
      if vehicle
      else "Unknown vehicle"
  )
  return f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Consultation Report - {consultation.license_plate}</title>
    <style>
      body {{
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #0f172a;
        font-size: 14px;
        line-height: 1.5;
      }}
      .header {{
        border-bottom: 2px solid {BRAND_PRIMARY_COLOR};
        margin-bottom: 16px;
        padding-bottom: 8px;
      }}
      .brand-title {{
        font-size: 20px;
        font-weight: 700;
        color: {BRAND_PRIMARY_COLOR};
      }}
      .meta {{
        font-size: 11px;
        color: #64748b;
      }}
      h2 {{
        font-size: 16px;
        margin-top: 16px;
        margin-bottom: 4px;
      }}
      pre {{
        white-space: pre-wrap;
        word-wrap: break-word;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 12px;
        background-color: #0f172a;
        color: #e2e8f0;
        padding: 8px;
        border-radius: 6px;
      }}
      .section {{
        margin-bottom: 12px;
      }}
      .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: .04em;
        background-color: #e0f2fe;
        color: #0369a1;
      }}
    </style>
  </head>
  <body>
    <div class="header">
      <div class="brand-title">Vehicle Diagnostics AI</div>
      <div class="meta">
        Consultation ID: {consultation.id}<br/>
        Technician: {tech_name}<br/>
        Created at: {consultation.created_at}
      </div>
    </div>

    <div class="section">
      <h2>Vehicle</h2>
      <div class="meta">
        License plate: <strong>{consultation.license_plate}</strong><br/>
        {header_vehicle}<br/>
        VIN: {vehicle.vin if vehicle else "N/A"}
      </div>
    </div>

    <div class="section">
      <h2>Technician description</h2>
      <pre>{consultation.query}</pre>
    </div>

    <div class="section">
      <h2>AI diagnostic report</h2>
      <div class="meta">
        <span class="badge">{consultation.ai_model_used}</span>
        &nbsp;Tokens: {consultation.total_tokens}
      </div>
      <pre>{consultation.ai_response}</pre>
    </div>

    {"<div class='section'><h2>Resolution notes</h2><pre>" + (consultation.resolution_notes or '') + "</pre></div>" if consultation.resolution_notes else ""}
  </body>
</html>
  """


def generate_consultation_pdf(
    db: Session,
    *,
    consultation: Consultation,
    user: Optional[User],
    vehicle: Optional[Vehicle],
    force_regenerate: bool = False,
) -> ConsultationPDF:
  """Generate (or reuse) a PDF for a consultation."""
  if HTML is None or CSS is None:
    raise RuntimeError(
        "PDF generation is not available in this environment. "
        "Please install 'weasyprint' (and its system dependencies) to enable PDF reports."
    )

  existing: ConsultationPDF | None = (
      db.query(ConsultationPDF)
      .filter(ConsultationPDF.consultation_id == str(consultation.id))
      .first()
  )

  if existing and not force_regenerate and os.path.exists(existing.file_path):
    return existing

  out_dir = _ensure_output_dir()
  filename = f"consultation-{consultation.id}.pdf"
  file_path = out_dir / filename

  html = _build_html(consultation, user, vehicle)

  HTML(string=html).write_pdf(
      target=str(file_path),
      stylesheets=[CSS(string="@page { size: A4; margin: 16mm; }")],
  )

  size = file_path.stat().st_size

  if existing:
    existing.file_path = str(file_path)
    existing.file_size_bytes = size
    pdf_record = existing
  else:
    pdf_record = ConsultationPDF(
        consultation_id=str(consultation.id),
        file_path=str(file_path),
        file_size_bytes=size,
    )
    db.add(pdf_record)

  db.commit()
  db.refresh(pdf_record)
  return pdf_record


def _build_chat_thread_html(
    thread: ChatThread,
    messages: list[ChatMessage],
    user: User | None,
    vehicle: Vehicle | None,
) -> str:
    """Build HTML for chat thread PDF report."""
    tech_name = getattr(user, "username", "Technician")
    tech_email = getattr(user, "email", "N/A")
    
    # Format date and time
    created_at = thread.created_at.strftime("%Y-%m-%d %H:%M:%S") if thread.created_at else "N/A"
    last_message_at = thread.last_message_at.strftime("%Y-%m-%d %H:%M:%S") if thread.last_message_at else "N/A"
    
    # Vehicle information
    header_vehicle = (
        f"{vehicle.make or ''} {vehicle.model or ''} {vehicle.year or ''}".strip()
        if vehicle
        else "Unknown vehicle"
    )
    vehicle_vin = vehicle.vin if vehicle else "N/A"
    
    # Handle vehicle_km - could be Decimal, int, float, or None
    # Convert to int for safe formatting
    vehicle_km = None
    if thread.vehicle_km is not None:
        try:
            # Handle Decimal, int, float, or string
            vehicle_km = int(float(str(thread.vehicle_km)))
        except (ValueError, TypeError, AttributeError):
            vehicle_km = None
    elif vehicle and vehicle.current_km is not None:
        try:
            vehicle_km = int(float(str(vehicle.current_km)))
        except (ValueError, TypeError, AttributeError):
            vehicle_km = None
    
    # Handle total_tokens - ensure it's an integer
    total_tokens = 0
    if thread.total_tokens is not None:
        try:
            total_tokens = int(thread.total_tokens)
        except (ValueError, TypeError):
            total_tokens = 0
    
    # Handle estimated_cost - convert Decimal to float safely
    estimated_cost_str = ""
    if thread.estimated_cost is not None:
        try:
            cost_value = float(str(thread.estimated_cost))
            if cost_value != 0:
                estimated_cost_str = f"${cost_value:.4f}"
        except (ValueError, TypeError, AttributeError):
            estimated_cost_str = ""
    
    # Build messages HTML
    messages_html = ""
    for msg in messages:
        if msg.role == "user":
            messages_html += f"""
            <div class="message user-message">
              <div class="message-header">
                <strong>Technician Query</strong>
                <span class="message-time">{msg.created_at.strftime("%H:%M:%S") if msg.created_at else ""}</span>
              </div>
              <div class="message-content">{_escape_html(msg.content)}</div>
            </div>
            """
        elif msg.role == "assistant":
            model_badge = f'<span class="badge">{msg.ai_model_used or "AI"}</span>' if msg.ai_model_used else ""
            tokens_info = f'<span class="tokens-info">Tokens: {msg.total_tokens or 0}</span>' if (msg.total_tokens and msg.total_tokens > 0) else ""
            messages_html += f"""
            <div class="message ai-message">
              <div class="message-header">
                <strong>AI Response</strong>
                {model_badge}
                {tokens_info}
                <span class="message-time">{msg.created_at.strftime("%H:%M:%S") if msg.created_at else ""}</span>
              </div>
              <div class="message-content">{_escape_html(msg.content)}</div>
            </div>
            """
    
    # Error codes
    error_codes_html = ""
    if thread.error_codes:
        codes = [code.strip() for code in thread.error_codes.split(",") if code.strip()]
        if codes:
            error_codes_html = f"""
            <div class="section">
              <h2>Error Codes (DTC)</h2>
              <div class="error-codes">
                {", ".join([f'<span class="dtc-badge">{code}</span>' for code in codes])}
              </div>
            </div>
            """
    
    # Vehicle context
    vehicle_context_html = ""
    if thread.vehicle_context:
        vehicle_context_html = f"""
        <div class="section">
          <h2>Additional Vehicle Context</h2>
          <pre>{_escape_html(thread.vehicle_context)}</pre>
        </div>
        """
    
    return f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Diagnostic Report - {thread.license_plate}</title>
    <style>
      body {{
        font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #0f172a;
        font-size: 14px;
        line-height: 1.6;
      }}
      .header {{
        border-bottom: 3px solid {BRAND_PRIMARY_COLOR};
        margin-bottom: 20px;
        padding-bottom: 12px;
      }}
      .brand-title {{
        font-size: 24px;
        font-weight: 700;
        color: {BRAND_PRIMARY_COLOR};
        margin-bottom: 8px;
      }}
      .meta {{
        font-size: 11px;
        color: #64748b;
        line-height: 1.8;
      }}
      .meta-row {{
        display: flex;
        justify-content: space-between;
        margin-bottom: 4px;
      }}
      .meta-label {{
        font-weight: 600;
        color: #475569;
      }}
      h2 {{
        font-size: 16px;
        margin-top: 20px;
        margin-bottom: 8px;
        color: {BRAND_PRIMARY_COLOR};
        border-bottom: 1px solid #e2e8f0;
        padding-bottom: 4px;
      }}
      .section {{
        margin-bottom: 20px;
        page-break-inside: avoid;
      }}
      .message {{
        margin-bottom: 16px;
        padding: 12px;
        border-radius: 8px;
        page-break-inside: avoid;
      }}
      .user-message {{
        background-color: #f1f5f9;
        border-left: 4px solid #3b82f6;
      }}
      .ai-message {{
        background-color: #fef3c7;
        border-left: 4px solid #f59e0b;
      }}
      .message-header {{
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        font-size: 12px;
        font-weight: 600;
        color: #475569;
      }}
      .message-time {{
        margin-left: auto;
        font-size: 10px;
        color: #94a3b8;
        font-weight: normal;
      }}
      .message-content {{
        white-space: pre-wrap;
        word-wrap: break-word;
        font-size: 13px;
        line-height: 1.6;
        color: #0f172a;
      }}
      .badge {{
        display: inline-block;
        padding: 2px 8px;
        border-radius: 999px;
        font-size: 10px;
        text-transform: uppercase;
        letter-spacing: .04em;
        background-color: #e0f2fe;
        color: #0369a1;
        font-weight: 600;
      }}
      .tokens-info {{
        font-size: 10px;
        color: #64748b;
        font-weight: normal;
      }}
      pre {{
        white-space: pre-wrap;
        word-wrap: break-word;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 12px;
        background-color: #f8fafc;
        color: #0f172a;
        padding: 12px;
        border-radius: 6px;
        border: 1px solid #e2e8f0;
      }}
      .error-codes {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
      }}
      .dtc-badge {{
        display: inline-block;
        padding: 4px 12px;
        border-radius: 6px;
        font-family: monospace;
        font-size: 12px;
        font-weight: 600;
        background-color: #fef3c7;
        color: #92400e;
        border: 1px solid #fbbf24;
      }}
      .summary {{
        background-color: #f8fafc;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #e2e8f0;
        margin-bottom: 20px;
      }}
      .summary-row {{
        display: flex;
        justify-content: space-between;
        padding: 4px 0;
        font-size: 12px;
      }}
      .summary-label {{
        font-weight: 600;
        color: #475569;
      }}
      .summary-value {{
        color: #0f172a;
      }}
    </style>
  </head>
  <body>
    <div class="header">
      <div class="brand-title">Vehicle Diagnostics AI</div>
      <div class="meta">
        <div class="meta-row">
          <span class="meta-label">Thread ID:</span>
          <span>{thread.id}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Technician:</span>
          <span>{tech_name} ({tech_email})</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Created:</span>
          <span>{created_at}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Last Message:</span>
          <span>{last_message_at}</span>
        </div>
        <div class="meta-row">
          <span class="meta-label">Status:</span>
          <span>{thread.status.upper()} {"(Resolved)" if thread.is_resolved else "(Pending)"}</span>
        </div>
      </div>
    </div>

    <div class="section">
      <h2>Vehicle Information</h2>
      <div class="summary">
        <div class="summary-row">
          <span class="summary-label">Registration Number (License Plate):</span>
          <span class="summary-value"><strong>{thread.license_plate}</strong></span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Vehicle:</span>
          <span class="summary-value">{header_vehicle}</span>
        </div>
        {f'<div class="summary-row"><span class="summary-label">VIN:</span><span class="summary-value">{vehicle_vin}</span></div>' if vehicle_vin != "N/A" else ""}
        {f'<div class="summary-row"><span class="summary-label">Mileage (km):</span><span class="summary-value">{vehicle_km:,}</span></div>' if (vehicle_km is not None and isinstance(vehicle_km, (int, float))) else ""}
      </div>
    </div>

    {error_codes_html}

    {vehicle_context_html}

    <div class="section">
      <h2>Conversation History</h2>
      <div class="summary">
        <div class="summary-row">
          <span class="summary-label">Total Messages:</span>
          <span class="summary-value">{len(messages)}</span>
        </div>
        <div class="summary-row">
          <span class="summary-label">Total Tokens Used:</span>
          <span class="summary-value">{total_tokens:,}</span>
        </div>
        {f'<div class="summary-row"><span class="summary-label">Estimated Cost:</span><span class="summary-value">{estimated_cost_str}</span></div>' if estimated_cost_str else ""}
      </div>
      {messages_html}
    </div>

    <div class="section" style="margin-top: 40px; padding-top: 20px; border-top: 2px solid #e2e8f0;">
      <div class="meta" style="text-align: center; color: #94a3b8;">
        Generated on {datetime.now().strftime("%Y-%m-%d %H:%M:%S")} | Vehicle Diagnostics AI Platform
      </div>
    </div>
  </body>
</html>
    """


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def generate_chat_thread_pdf(
    db: Session,
    *,
    thread: ChatThread,
    messages: list[ChatMessage],
    user: Optional[User],
    vehicle: Optional[Vehicle],
    force_regenerate: bool = False,
) -> ChatThreadPDF:
    """Generate (or reuse) a PDF for a chat thread."""
    import logging
    import uuid as uuid_lib
    logger = logging.getLogger(__name__)
    
    if HTML is None or CSS is None:
        raise RuntimeError(
            "PDF generation is not available in this environment. "
            "Please install 'weasyprint' (and its system dependencies) to enable PDF reports."
        )

    try:
        existing: ChatThreadPDF | None = (
            db.query(ChatThreadPDF)
            .filter(ChatThreadPDF.thread_id == thread.id)
            .first()
        )

        if existing and not force_regenerate and os.path.exists(existing.file_path):
            logger.info(f"Reusing existing PDF for thread {thread.id}")
            return existing

        logger.info(f"Generating new PDF for thread {thread.id}")
        out_dir = _ensure_output_dir()
        logger.info(f"PDF output directory: {out_dir}")
        
        filename = f"chat-thread-{thread.id}.pdf"
        file_path = out_dir / filename

        html = _build_chat_thread_html(thread, messages, user, vehicle)
        logger.debug(f"HTML generated, length: {len(html)}")
        
        # Validate HTML before attempting PDF generation
        if not html or len(html.strip()) < 100:
            logger.error(f"Generated HTML is too short or empty: {len(html) if html else 0} characters")
            raise RuntimeError("Failed to generate valid HTML content for PDF")
        
        # Check for common HTML issues that could break WeasyPrint
        if "<html" not in html.lower() or "</html>" not in html.lower():
            logger.error("Generated HTML is missing required HTML tags")
            raise RuntimeError("Generated HTML is malformed")

        try:
            # Validate HTML is not empty
            if not html or len(html.strip()) == 0:
                raise RuntimeError("Generated HTML is empty")
            
            logger.debug(f"Attempting to write PDF to {file_path}")
            HTML(string=html).write_pdf(
                target=str(file_path),
                stylesheets=[CSS(string="@page { size: A4; margin: 16mm; }")],
            )
            logger.info(f"PDF written to: {file_path}")
        except ImportError as e:
            logger.error(f"WeasyPrint import error: {e}", exc_info=True)
            raise RuntimeError("WeasyPrint is not properly installed. Please check system dependencies.")
        except OSError as e:
            logger.error(f"OS error writing PDF file (permissions?): {e}", exc_info=True)
            raise RuntimeError(f"Cannot write PDF file (permission or disk space issue): {str(e)}")
        except Exception as e:
            logger.error(f"Error writing PDF file: {type(e).__name__}: {e}", exc_info=True)
            # Provide more specific error message
            error_msg = str(e)
            if "super" in error_msg.lower() or "transform" in error_msg.lower():
                raise RuntimeError("WeasyPrint version incompatibility. Please ensure WeasyPrint is compatible with Python version.")
            raise RuntimeError(f"Failed to write PDF file: {error_msg}")

        if not os.path.exists(file_path):
            logger.error(f"PDF file was not created at {file_path}")
            # Check if directory exists and is writable
            if not os.path.exists(out_dir):
                raise RuntimeError(f"PDF output directory does not exist: {out_dir}")
            if not os.access(out_dir, os.W_OK):
                raise RuntimeError(f"PDF output directory is not writable: {out_dir}")
            raise RuntimeError(f"PDF file was not created at {file_path}")

        size = file_path.stat().st_size
        if size == 0:
            logger.warning(f"PDF file is empty (0 bytes): {file_path}")
            raise RuntimeError("Generated PDF file is empty")
        logger.info(f"PDF file size: {size} bytes")

        if existing:
            existing.file_path = str(file_path)
            existing.file_size_bytes = size
            pdf_record = existing
        else:
            pdf_record = ChatThreadPDF(
                id=uuid_lib.uuid4(),
                thread_id=thread.id,
                workshop_id=thread.workshop_id,
                file_path=str(file_path),
                file_size_bytes=size,
            )
            db.add(pdf_record)

        db.commit()
        db.refresh(pdf_record)
        logger.info(f"PDF record created/updated: {pdf_record.id}")
        return pdf_record
    except Exception as e:
        logger.error(f"Error in generate_chat_thread_pdf: {e}", exc_info=True)
        db.rollback()
        raise



