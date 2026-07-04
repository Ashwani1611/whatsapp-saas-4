from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.models.client import Client
from app.models.user import User, UserRole
from app.models.transaction import Transaction
from app.utils.auth import require_superadmin, hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["Admin"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ClientCreate(BaseModel):
    business_name:   str
    email:           EmailStr
    phone:           Optional[str] = None
    custom_domain:   Optional[str] = None
    subdomain:       Optional[str] = None
    plan:            str = "basic"
    admin_name:      str
    admin_password:  str


class ClientUpdate(BaseModel):
    business_name: Optional[str] = None
    custom_domain: Optional[str] = None
    subdomain:     Optional[str] = None
    plan:          Optional[str] = None
    is_active:     Optional[bool] = None


class TopupRequest(BaseModel):
    amount:      float
    description: Optional[str] = "Manual top-up by admin"


# ── List all clients ──────────────────────────────────────────────────────────
@router.get("/clients")
def list_clients(
    page:   int = Query(1, ge=1),
    limit:  int = Query(20, le=100),
    search: Optional[str] = None,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    query = db.query(Client)
    if search:
        query = query.filter(Client.business_name.ilike(f"%{search}%"))

    total   = query.count()
    clients = query.order_by(Client.created_at.desc()) \
                   .offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "clients": [
            {
                "id":              c.id,
                "business_name":   c.business_name,
                "email":           c.email,
                "custom_domain":   c.custom_domain,
                "subdomain":       c.subdomain,
                "plan":            c.plan,
                "wallet_balance":  float(c.wallet_balance),
                "is_active":       c.is_active,
                "created_at":      c.created_at,
            }
            for c in clients
        ]
    }


# ── Create a new client (onboard) ─────────────────────────────────────────────
@router.post("/clients")
def create_client(
    payload: ClientCreate,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    existing = db.query(Client).filter(Client.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Client with this email already exists")

    if payload.custom_domain:
        domain_taken = db.query(Client).filter(Client.custom_domain == payload.custom_domain).first()
        if domain_taken:
            raise HTTPException(status_code=400, detail="This domain is already in use")

    if payload.subdomain:
        subdomain_taken = db.query(Client).filter(Client.subdomain == payload.subdomain).first()
        if subdomain_taken:
            raise HTTPException(status_code=400, detail="This subdomain is already in use")

    client = Client(
        business_name = payload.business_name,
        email         = payload.email,
        phone         = payload.phone,
        custom_domain = payload.custom_domain,
        subdomain     = payload.subdomain,
        plan          = payload.plan,
    )
    db.add(client)
    db.flush()

    # Create the client admin user
    admin_user = User(
        client_id     = client.id,
        name          = payload.admin_name,
        email         = payload.email,
        password_hash = hash_password(payload.admin_password),
        role          = UserRole.client_admin,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(client)

    return {
        "message":   "Client onboarded successfully",
        "client_id": client.id,
        "login_email": payload.email
    }


# ── Update client ──────────────────────────────────────────────────────────────
@router.put("/clients/{client_id}")
def update_client(
    client_id: int,
    payload:   ClientUpdate,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(client, field, value)

    client.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Client updated"}


# ── Suspend / reactivate client ───────────────────────────────────────────────
@router.put("/clients/{client_id}/suspend")
def suspend_client(
    client_id: int,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.is_active = False
    db.commit()
    return {"message": "Client suspended"}


@router.put("/clients/{client_id}/reactivate")
def reactivate_client(
    client_id: int,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    client.is_active = True
    db.commit()
    return {"message": "Client reactivated"}


# ── Manual wallet top-up ──────────────────────────────────────────────────────
@router.post("/clients/{client_id}/topup")
def manual_topup(
    client_id: int,
    payload:   TopupRequest,
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    amount = Decimal(str(payload.amount))
    client.wallet_balance += amount

    txn = Transaction(
        client_id     = client_id,
        amount        = amount,
        type          = "topup",
        description   = payload.description,
        balance_after = client.wallet_balance
    )
    db.add(txn)
    db.commit()

    return {
        "message":        "Wallet topped up",
        "wallet_balance": float(client.wallet_balance)
    }


# ── Platform-wide stats ───────────────────────────────────────────────────────
@router.get("/stats")
def platform_stats(
    current_user: User = Depends(require_superadmin),
    db: Session        = Depends(get_db)
):
    from app.models.message import Message
    from app.models.campaign import Campaign
    from sqlalchemy import func

    total_clients   = db.query(Client).count()
    active_clients  = db.query(Client).filter(Client.is_active == True).count()
    total_messages  = db.query(Message).count()
    total_campaigns = db.query(Campaign).count()
    total_revenue   = db.query(func.sum(Transaction.amount)).filter(
        Transaction.type == "topup"
    ).scalar() or 0

    return {
        "total_clients":   total_clients,
        "active_clients":  active_clients,
        "total_messages":  total_messages,
        "total_campaigns": total_campaigns,
        "total_revenue":   float(total_revenue),
    }
