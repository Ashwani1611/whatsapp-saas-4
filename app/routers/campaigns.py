from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from app.database import get_db
from app.models.campaign import Campaign, CampaignLog
from app.models.template import Template
from app.models.contact import Contact
from app.models.user import User
from app.utils.auth import require_client_admin, require_agent

router = APIRouter(prefix="/api/v1/campaigns", tags=["Campaigns"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class CampaignCreate(BaseModel):
    name:         str
    template_id:  int
    target_tags:  Optional[List[str]] = []    # empty = send to all contacts
    scheduled_at: Optional[datetime]  = None  # null = send immediately


class CampaignOut(BaseModel):
    id:              int
    name:            str
    template_id:     int
    target_tags:     List[str]
    status:          str
    scheduled_at:    Optional[datetime]
    started_at:      Optional[datetime]
    completed_at:    Optional[datetime]
    total_contacts:  int
    sent:            int
    delivered:       int
    read:            int
    failed:          int
    created_at:      datetime

    class Config:
        from_attributes = True


# ── List campaigns ────────────────────────────────────────────────────────────
@router.get("/", response_model=dict)
def list_campaigns(
    status: Optional[str] = None,
    page:   int = Query(1, ge=1),
    limit:  int = Query(20, le=100),
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    query = db.query(Campaign).filter(
        Campaign.client_id == current_user.client_id,
        Campaign.is_active == True
    )
    if status:
        query = query.filter(Campaign.status == status)

    total     = query.count()
    campaigns = query.order_by(Campaign.created_at.desc()) \
                     .offset((page - 1) * limit).limit(limit).all()

    return {
        "total":     total,
        "campaigns": [CampaignOut.from_orm(c) for c in campaigns]
    }


# ── Create campaign ───────────────────────────────────────────────────────────
@router.post("/", response_model=CampaignOut)
def create_campaign(
    payload: CampaignCreate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    # Validate template exists and is approved
    template = db.query(Template).filter(
        Template.id        == payload.template_id,
        Template.client_id == client_id,
        Template.status    == "approved",
        Template.is_active == True
    ).first()
    if not template:
        raise HTTPException(status_code=400, detail="Template not found or not approved yet")

    campaign = Campaign(
        client_id    = client_id,
        template_id  = payload.template_id,
        name         = payload.name,
        target_tags  = payload.target_tags or [],
        status       = "scheduled" if payload.scheduled_at else "draft",
        scheduled_at = payload.scheduled_at,
    )
    db.add(campaign)
    db.commit()
    db.refresh(campaign)
    return campaign


# ── Send campaign now ─────────────────────────────────────────────────────────
@router.post("/{campaign_id}/send")
def send_campaign(
    campaign_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    campaign = db.query(Campaign).filter(
        Campaign.id        == campaign_id,
        Campaign.client_id == current_user.client_id,
        Campaign.is_active == True
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status in ["running", "completed"]:
        raise HTTPException(status_code=400, detail=f"Campaign is already {campaign.status}")

    # Check wallet balance
    from app.models.client import Client
    client = db.query(Client).filter(Client.id == current_user.client_id).first()
    if client.wallet_balance <= 0:
        raise HTTPException(status_code=400, detail="Insufficient wallet balance. Please top up.")

    # Queue the broadcast task
    from app.tasks.broadcast import send_broadcast_campaign
    send_broadcast_campaign.delay(campaign_id)

    campaign.status = "running"
    db.commit()

    return {"message": "Campaign queued successfully", "campaign_id": campaign_id}


# ── Campaign analytics ────────────────────────────────────────────────────────
@router.get("/{campaign_id}/analytics")
def campaign_analytics(
    campaign_id: int,
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    campaign = db.query(Campaign).filter(
        Campaign.id        == campaign_id,
        Campaign.client_id == current_user.client_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    total = campaign.total_contacts or 1  # avoid division by zero

    return {
        "campaign_id":     campaign.id,
        "name":            campaign.name,
        "status":          campaign.status,
        "total_contacts":  campaign.total_contacts,
        "sent":            campaign.sent,
        "delivered":       campaign.delivered,
        "read":            campaign.read,
        "failed":          campaign.failed,
        "delivery_rate":   round((campaign.delivered / total) * 100, 2),
        "read_rate":       round((campaign.read / total) * 100, 2),
        "fail_rate":       round((campaign.failed / total) * 100, 2),
        "started_at":      campaign.started_at,
        "completed_at":    campaign.completed_at,
    }


# ── Campaign logs (per contact status) ───────────────────────────────────────
@router.get("/{campaign_id}/logs")
def campaign_logs(
    campaign_id: int,
    status:  Optional[str] = None,
    page:    int = Query(1, ge=1),
    limit:   int = Query(50, le=200),
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    # Verify campaign belongs to client
    campaign = db.query(Campaign).filter(
        Campaign.id        == campaign_id,
        Campaign.client_id == current_user.client_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    query = db.query(CampaignLog).filter(CampaignLog.campaign_id == campaign_id)
    if status:
        query = query.filter(CampaignLog.status == status)

    total = query.count()
    logs  = query.offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "logs": [
            {
                "contact_id":      log.contact_id,
                "contact_name":    log.contact.name,
                "contact_phone":   log.contact.phone,
                "status":          log.status,
                "sent_at":         log.sent_at,
                "delivered_at":    log.delivered_at,
                "read_at":         log.read_at,
                "failed_at":       log.failed_at,
                "error_message":   log.error_message,
            }
            for log in logs
        ]
    }


# ── Delete campaign ───────────────────────────────────────────────────────────
@router.delete("/{campaign_id}")
def delete_campaign(
    campaign_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    campaign = db.query(Campaign).filter(
        Campaign.id        == campaign_id,
        Campaign.client_id == current_user.client_id
    ).first()
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    if campaign.status == "running":
        raise HTTPException(status_code=400, detail="Cannot delete a running campaign")

    campaign.is_active = False
    db.commit()
    return {"message": "Campaign deleted"}
