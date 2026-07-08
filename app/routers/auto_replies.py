from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.transaction import AutoReply
from app.models.user import User
from app.utils.auth import require_client_admin, require_agent

router = APIRouter(prefix="/api/v1/auto-replies", tags=["Auto Replies"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class AutoReplyCreate(BaseModel):
    trigger_type:     str            # welcome / keyword / fallback
    keyword:          Optional[str] = None
    response_type:    str            # text / template
    response_content: dict           # {"text": "..."} or {"template_id": 1}


class AutoReplyUpdate(BaseModel):
    keyword:          Optional[str] = None
    response_type:    Optional[str] = None
    response_content: Optional[dict] = None
    is_active:        Optional[bool] = None


class AutoReplyOut(BaseModel):
    id:               int
    trigger_type:     str
    keyword:          Optional[str]
    response_type:    str
    response_content: dict
    is_active:        bool
    created_at:       datetime

    class Config:
        from_attributes = True


# ── List all rules for this client ────────────────────────────────────────────
@router.get("/", response_model=list[AutoReplyOut])
def list_auto_replies(
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    rules = db.query(AutoReply).filter(
        AutoReply.client_id == current_user.client_id
    ).order_by(AutoReply.trigger_type, AutoReply.created_at.desc()).all()
    return rules


# ── Create a rule ──────────────────────────────────────────────────────────────
@router.post("/", response_model=AutoReplyOut)
def create_auto_reply(
    payload: AutoReplyCreate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    if payload.trigger_type not in ["welcome", "keyword", "fallback"]:
        raise HTTPException(status_code=400, detail="trigger_type must be welcome, keyword, or fallback")
    if payload.trigger_type == "keyword" and not payload.keyword:
        raise HTTPException(status_code=400, detail="keyword is required for keyword-type rules")
    if payload.response_type not in ["text", "template"]:
        raise HTTPException(status_code=400, detail="response_type must be text or template")
    if payload.response_type == "text" and not payload.response_content.get("text"):
        raise HTTPException(status_code=400, detail="response_content.text is required")
    if payload.response_type == "template" and not payload.response_content.get("template_id"):
        raise HTTPException(status_code=400, detail="response_content.template_id is required")

    # Welcome and fallback are singletons — deactivate any existing rule of the same type
    if payload.trigger_type in ["welcome", "fallback"]:
        db.query(AutoReply).filter(
            AutoReply.client_id    == client_id,
            AutoReply.trigger_type == payload.trigger_type
        ).update({"is_active": False})

    rule = AutoReply(
        client_id         = client_id,
        trigger_type      = payload.trigger_type,
        keyword           = payload.keyword,
        response_type     = payload.response_type,
        response_content  = payload.response_content,
        is_active         = True,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


# ── Update a rule ──────────────────────────────────────────────────────────────
@router.put("/{rule_id}", response_model=AutoReplyOut)
def update_auto_reply(
    rule_id: int,
    payload: AutoReplyUpdate,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    rule = db.query(AutoReply).filter(
        AutoReply.id        == rule_id,
        AutoReply.client_id == current_user.client_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    for field, value in payload.dict(exclude_unset=True).items():
        setattr(rule, field, value)

    rule.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(rule)
    return rule


# ── Delete a rule ──────────────────────────────────────────────────────────────
@router.delete("/{rule_id}")
def delete_auto_reply(
    rule_id: int,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    rule = db.query(AutoReply).filter(
        AutoReply.id        == rule_id,
        AutoReply.client_id == current_user.client_id
    ).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted"}