from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import pandas as pd
import io

from app.database import get_db
from app.models.contact import Contact
from app.models.user import User
from app.utils.auth import require_agent, require_client_admin

router = APIRouter(prefix="/api/v1/contacts", tags=["Contacts"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ContactCreate(BaseModel):
    name:               str
    phone:              str
    email:              Optional[str] = None
    tags:               Optional[List[str]] = []
    custom_attributes:  Optional[dict] = {}


class ContactUpdate(BaseModel):
    name:               Optional[str] = None
    email:              Optional[str] = None
    tags:               Optional[List[str]] = None
    custom_attributes:  Optional[dict] = None
    opted_in:           Optional[bool] = None


class ContactOut(BaseModel):
    id:                 int
    name:               str
    phone:              str
    email:              Optional[str]
    tags:               List[str]
    custom_attributes:  dict
    opted_in:           bool
    last_contacted_at:  Optional[datetime]
    created_at:         datetime

    class Config:
        from_attributes = True


# ── List contacts ─────────────────────────────────────────────────────────────
@router.get("/", response_model=dict)
def list_contacts(
    page:    int = Query(1, ge=1),
    limit:   int = Query(20, le=100),
    search:  Optional[str] = None,
    tag:     Optional[str] = None,
    current_user: User     = Depends(require_agent),
    db: Session            = Depends(get_db)
):
    client_id = current_user.client_id
    query = db.query(Contact).filter(
        Contact.client_id == client_id,
        Contact.is_active == True
    )

    if search:
        query = query.filter(
            or_(
                Contact.name.ilike(f"%{search}%"),
                Contact.phone.ilike(f"%{search}%"),
                Contact.email.ilike(f"%{search}%"),
            )
        )
    if tag:
        query = query.filter(Contact.tags.contains([tag]))

    total   = query.count()
    contacts = query.order_by(Contact.created_at.desc()) \
                    .offset((page - 1) * limit).limit(limit).all()

    return {
        "total":    total,
        "page":     page,
        "limit":    limit,
        "pages":    (total + limit - 1) // limit,
        "contacts": [ContactOut.from_orm(c) for c in contacts]
    }


# ── Create contact ────────────────────────────────────────────────────────────
@router.post("/", response_model=ContactOut)
def create_contact(
    payload: ContactCreate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    # Check duplicate phone for this client
    existing = db.query(Contact).filter(
        Contact.client_id == client_id,
        Contact.phone     == payload.phone
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Contact with this phone already exists")

    contact = Contact(
        client_id         = client_id,
        name              = payload.name,
        phone             = payload.phone,
        email             = payload.email,
        tags              = payload.tags or [],
        custom_attributes = payload.custom_attributes or {},
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)
    return contact


# ── Get single contact ────────────────────────────────────────────────────────
@router.get("/{contact_id}", response_model=ContactOut)
def get_contact(
    contact_id: int,
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    contact = db.query(Contact).filter(
        Contact.id        == contact_id,
        Contact.client_id == current_user.client_id,
        Contact.is_active == True
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


# ── Update contact ────────────────────────────────────────────────────────────
@router.put("/{contact_id}", response_model=ContactOut)
def update_contact(
    contact_id: int,
    payload:    ContactUpdate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    contact = db.query(Contact).filter(
        Contact.id        == contact_id,
        Contact.client_id == current_user.client_id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(contact, field, value)

    contact.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(contact)
    return contact


# ── Soft delete contact ───────────────────────────────────────────────────────
@router.delete("/{contact_id}")
def delete_contact(
    contact_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    contact = db.query(Contact).filter(
        Contact.id        == contact_id,
        Contact.client_id == current_user.client_id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    contact.is_active = False
    db.commit()
    return {"message": "Contact deleted"}


# ── CSV Import ────────────────────────────────────────────────────────────────
@router.post("/import")
async def import_contacts(
    file: UploadFile        = File(...),
    current_user: User      = Depends(require_client_admin),
    db: Session             = Depends(get_db)
):
    """
    CSV format expected:
    name, phone, email (optional), tags (optional - comma separated)
    """
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files allowed")

    contents = await file.read()
    df = pd.read_csv(io.BytesIO(contents))

    # Normalize column names
    df.columns = [c.strip().lower() for c in df.columns]

    if "name" not in df.columns or "phone" not in df.columns:
        raise HTTPException(status_code=400, detail="CSV must have 'name' and 'phone' columns")

    client_id = current_user.client_id
    created = 0
    skipped = 0
    errors  = []

    for _, row in df.iterrows():
        try:
            phone = str(row["phone"]).strip()
            name  = str(row["name"]).strip()

            if not phone or not name:
                skipped += 1
                continue

            # Add country code if missing
            if not phone.startswith("+"):
                phone = "+91" + phone.lstrip("0")

            existing = db.query(Contact).filter(
                Contact.client_id == client_id,
                Contact.phone     == phone
            ).first()
            if existing:
                skipped += 1
                continue

            tags = []
            if "tags" in df.columns and pd.notna(row.get("tags")):
                tags = [t.strip() for t in str(row["tags"]).split(",") if t.strip()]

            contact = Contact(
                client_id = client_id,
                name      = name,
                phone     = phone,
                email     = str(row.get("email", "")).strip() or None,
                tags      = tags,
            )
            db.add(contact)
            created += 1

        except Exception as e:
            errors.append(str(e))

    db.commit()

    return {
        "message": f"Import complete",
        "created": created,
        "skipped": skipped,
        "errors":  errors[:10]  # return first 10 errors only
    }


# ── All tags for this client ──────────────────────────────────────────────────
@router.get("/meta/tags")
def get_all_tags(
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    contacts = db.query(Contact.tags).filter(
        Contact.client_id == current_user.client_id,
        Contact.is_active == True
    ).all()

    all_tags = set()
    for row in contacts:
        if row.tags:
            all_tags.update(row.tags)

    return {"tags": sorted(list(all_tags))}
