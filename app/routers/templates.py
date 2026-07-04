from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models.template import Template
from app.models.wa_number import WANumber
from app.models.user import User
from app.utils.auth import require_client_admin, require_agent
from app.utils.encryption import decrypt
from app.services.whatsapp import WhatsAppService

router = APIRouter(prefix="/api/v1/templates", tags=["Templates"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class TemplateCreate(BaseModel):
    name:       str                  # must be lowercase, underscore, no spaces
    category:   str                  # marketing / utility / authentication
    language:   str = "en"
    components: dict                 # Meta template components structure


class TemplateOut(BaseModel):
    id:               int
    name:             str
    category:         str
    language:         str
    components:       dict
    meta_template_id: Optional[str]
    status:           str
    rejection_reason: Optional[str]
    created_at:       datetime

    class Config:
        from_attributes = True


# ── List templates ────────────────────────────────────────────────────────────
@router.get("/", response_model=dict)
def list_templates(
    status: Optional[str] = None,   # pending / approved / rejected
    page:   int = Query(1, ge=1),
    limit:  int = Query(20, le=100),
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    query = db.query(Template).filter(
        Template.client_id == current_user.client_id,
        Template.is_active == True
    )
    if status:
        query = query.filter(Template.status == status)

    total     = query.count()
    templates = query.order_by(Template.created_at.desc()) \
                     .offset((page - 1) * limit).limit(limit).all()

    return {
        "total":     total,
        "templates": [TemplateOut.from_orm(t) for t in templates]
    }


# ── Create + submit template ──────────────────────────────────────────────────
@router.post("/", response_model=TemplateOut)
def create_template(
    payload: TemplateCreate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    # Validate category
    if payload.category not in ["marketing", "utility", "authentication"]:
        raise HTTPException(status_code=400, detail="Invalid category")

    # Validate name (Meta rule: lowercase, underscores only)
    import re
    if not re.match(r'^[a-z0-9_]+$', payload.name):
        raise HTTPException(
            status_code=400,
            detail="Template name must be lowercase letters, numbers, underscores only"
        )

    # Check duplicate name for this client
    existing = db.query(Template).filter(
        Template.client_id == client_id,
        Template.name      == payload.name,
        Template.is_active == True
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Template with this name already exists")

    # Save template locally first
    template = Template(
        client_id  = client_id,
        name       = payload.name,
        category   = payload.category,
        language   = payload.language,
        components = payload.components,
        status     = "pending"
    )
    db.add(template)
    db.flush()

    # Submit to Meta
    wa_number = db.query(WANumber).filter(
        WANumber.client_id == client_id,
        WANumber.status    == "connected",
        WANumber.is_active == True
    ).first()

    if wa_number:
        try:
            access_token = decrypt(wa_number.access_token)
            wa_service   = WhatsAppService(wa_number.phone_number_id, access_token)

            result = wa_service.submit_template(
                name       = payload.name,
                category   = payload.category,
                language   = payload.language,
                components = payload.components.get("message_components", [])
            )
            template.meta_template_id = result.get("id")
            template.status           = result.get("status", "pending").lower()

        except Exception as e:
            # Save locally even if Meta submission fails
            template.status = "pending"

    db.commit()
    db.refresh(template)
    return template


# ── Get template ──────────────────────────────────────────────────────────────
@router.get("/{template_id}", response_model=TemplateOut)
def get_template(
    template_id: int,
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    template = db.query(Template).filter(
        Template.id        == template_id,
        Template.client_id == current_user.client_id,
        Template.is_active == True
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return template


# ── Delete template ───────────────────────────────────────────────────────────
@router.delete("/{template_id}")
def delete_template(
    template_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    template = db.query(Template).filter(
        Template.id        == template_id,
        Template.client_id == current_user.client_id
    ).first()
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")

    template.is_active = False
    db.commit()
    return {"message": "Template deleted"}


# ── Sync approval status from Meta ───────────────────────────────────────────
@router.post("/sync")
def sync_templates(
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    wa_number = db.query(WANumber).filter(
        WANumber.client_id == client_id,
        WANumber.status    == "connected",
        WANumber.is_active == True
    ).first()
    if not wa_number:
        raise HTTPException(status_code=400, detail="No connected WhatsApp number")

    pending = db.query(Template).filter(
        Template.client_id == client_id,
        Template.status    == "pending",
        Template.is_active == True
    ).all()

    access_token = decrypt(wa_number.access_token)
    wa_service   = WhatsAppService(wa_number.phone_number_id, access_token)
    updated      = 0

    for template in pending:
        try:
            result = wa_service.get_template_status(wa_number.waba_id, template.name)
            data   = result.get("data", [])
            if data:
                meta_status = data[0].get("status", "").lower()
                if meta_status in ["approved", "rejected"]:
                    template.status           = meta_status
                    template.rejection_reason = data[0].get("rejected_reason")
                    updated += 1
        except Exception as e:
            continue

    db.commit()
    return {"message": f"Synced {updated} templates"}
