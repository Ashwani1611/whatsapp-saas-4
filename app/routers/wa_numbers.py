from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.wa_number import WANumber
from app.models.user import User
from app.utils.auth import require_client_admin
from app.utils.encryption import encrypt
from app.config import settings
import secrets

router = APIRouter(prefix="/api/v1/wa-numbers", tags=["WhatsApp Numbers"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class WANumberCreate(BaseModel):
    phone_number_id:      str
    display_phone_number: str
    waba_id:               str
    access_token:          str    # permanent token from Meta System User


class WANumberOut(BaseModel):
    id:                   int
    display_phone_number: str
    waba_id:              str
    status:               str
    webhook_verify_token: str

    class Config:
        from_attributes = True


# ── Onboard a new WhatsApp number ─────────────────────────────────────────────
@router.post("/onboard", response_model=WANumberOut)
def onboard_number(
    payload: WANumberCreate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    existing = db.query(WANumber).filter(
        WANumber.phone_number_id == payload.phone_number_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="This WhatsApp number is already connected")

    wa_number = WANumber(
        client_id             = client_id,
        phone_number_id       = payload.phone_number_id,
        display_phone_number  = payload.display_phone_number,
        waba_id                = payload.waba_id,
        access_token            = encrypt(payload.access_token),
        webhook_verify_token    = settings.WEBHOOK_VERIFY_TOKEN,
        status                  = "connected",
    )
    db.add(wa_number)
    db.commit()
    db.refresh(wa_number)
    return wa_number


# ── List client's WA numbers ──────────────────────────────────────────────────
@router.get("/", response_model=list[WANumberOut])
def list_numbers(
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    numbers = db.query(WANumber).filter(
        WANumber.client_id == current_user.client_id,
        WANumber.is_active == True
    ).all()
    return numbers


# ── Disconnect a number ───────────────────────────────────────────────────────
@router.delete("/{number_id}")
def disconnect_number(
    number_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    wa_number = db.query(WANumber).filter(
        WANumber.id        == number_id,
        WANumber.client_id == current_user.client_id
    ).first()
    if not wa_number:
        raise HTTPException(status_code=404, detail="Number not found")

    wa_number.is_active = False
    wa_number.status     = "disconnected"
    db.commit()
    return {"message": "WhatsApp number disconnected"}
