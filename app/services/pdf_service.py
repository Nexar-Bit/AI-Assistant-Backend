from __future__ import annotations

import os
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


BRAND_PRIMARY_COLOR = "#0ea5e9"  # sky-500


def _ensure_output_dir() -> Path:
  out = Path(settings.PDF_OUTPUT_DIR)
  out.mkdir(parents=True, exist_ok=True)
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


