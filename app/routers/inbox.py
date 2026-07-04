from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.database import get_db
from app.models.message import Message
from app.models.contact import Contact
from app.models.wa_number import WANumber
from app.models.user import User
from app.utils.auth import require_agent, require_client_admin
from app.utils.encryption import decrypt
from app.services.whatsapp import WhatsAppService

router = APIRouter(prefix="/api/v1/inbox", tags=["Inbox"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class ReplyRequest(BaseModel):
    message_type: str = "text"          # text / image / document
    text:         Optional[str] = None
    media_url:    Optional[str] = None
    caption:      Optional[str] = None
    filename:     Optional[str] = None


# ── List conversations (grouped by contact, latest message first) ────────────
@router.get("/conversations")
def list_conversations(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    # Get latest message per contact, ordered by most recent
    subq = db.query(
        Message.contact_id,
        func.max(Message.created_at).label("latest")
    ).filter(
        Message.client_id == client_id
    ).group_by(Message.contact_id).subquery()

    rows = db.query(Message, Contact).join(
        subq,
        (Message.contact_id == subq.c.contact_id) & (Message.created_at == subq.c.latest)
    ).join(
        Contact, Contact.id == Message.contact_id
    ).order_by(desc(Message.created_at)) \
     .offset((page - 1) * limit).limit(limit).all()

    conversations = []
    for msg, contact in rows:
        unread_count = db.query(Message).filter(
            Message.contact_id == contact.id,
            Message.direction  == "inbound",
            Message.status     != "read"
        ).count()

        conversations.append({
            "contact_id":      contact.id,
            "contact_name":    contact.name,
            "contact_phone":   contact.phone,
            "last_message":    msg.content,
            "last_message_at": msg.created_at,
            "direction":       msg.direction,
            "unread_count":    unread_count,
        })

    return {"conversations": conversations}


# ── Get message history for a contact ─────────────────────────────────────────
@router.get("/conversations/{contact_id}")
def get_conversation(
    contact_id: int,
    page:  int = Query(1, ge=1),
    limit: int = Query(50, le=200),
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    contact = db.query(Contact).filter(
        Contact.id        == contact_id,
        Contact.client_id == current_user.client_id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    total = db.query(Message).filter(Message.contact_id == contact_id).count()

    messages = db.query(Message).filter(
        Message.contact_id == contact_id,
        Message.client_id  == current_user.client_id
    ).order_by(desc(Message.created_at)) \
     .offset((page - 1) * limit).limit(limit).all()

    return {
        "contact": {
            "id":    contact.id,
            "name":  contact.name,
            "phone": contact.phone,
            "tags":  contact.tags,
        },
        "total": total,
        "messages": [
            {
                "id":           m.id,
                "direction":    m.direction,
                "message_type": m.message_type,
                "content":      m.content,
                "status":       m.status,
                "created_at":   m.created_at,
            }
            for m in reversed(messages)
        ]
    }


# ── Reply to a conversation ───────────────────────────────────────────────────
@router.post("/conversations/{contact_id}/reply")
def reply_to_conversation(
    contact_id: int,
    payload:    ReplyRequest,
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    client_id = current_user.client_id

    contact = db.query(Contact).filter(
        Contact.id        == contact_id,
        Contact.client_id == client_id
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    wa_number = db.query(WANumber).filter(
        WANumber.client_id == client_id,
        WANumber.status    == "connected",
        WANumber.is_active == True
    ).first()
    if not wa_number:
        raise HTTPException(status_code=400, detail="No connected WhatsApp number")

    access_token = decrypt(wa_number.access_token)
    wa_service   = WhatsAppService(wa_number.phone_number_id, access_token)

    try:
        if payload.message_type == "text":
            result  = wa_service.send_text(contact.phone, payload.text)
            content = {"text": payload.text}
        elif payload.message_type == "image":
            result  = wa_service.send_image(contact.phone, payload.media_url, payload.caption or "")
            content = {"url": payload.media_url, "caption": payload.caption}
        elif payload.message_type == "document":
            result  = wa_service.send_document(contact.phone, payload.media_url, payload.filename, payload.caption or "")
            content = {"url": payload.media_url, "filename": payload.filename, "caption": payload.caption}
        else:
            raise HTTPException(status_code=400, detail="Unsupported message type")

    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to send message: {str(e)}")

    message = Message(
        client_id       = client_id,
        contact_id       = contact_id,
        direction        = "outbound",
        message_type     = payload.message_type,
        content          = content,
        meta_message_id  = result.get("messages", [{}])[0].get("id"),
        status           = "sent",
        is_automated     = False,
    )
    db.add(message)
    contact.last_contacted_at = datetime.utcnow()
    db.commit()

    return {"message": "Reply sent", "message_id": message.id}


# ── Mark conversation messages as read ────────────────────────────────────────
@router.put("/conversations/{contact_id}/resolve")
def mark_resolved(
    contact_id: int,
    current_user: User = Depends(require_agent),
    db: Session        = Depends(get_db)
):
    updated = db.query(Message).filter(
        Message.contact_id == contact_id,
        Message.client_id  == current_user.client_id,
        Message.direction  == "inbound",
        Message.status     != "read"
    ).update({"status": "read"})
    db.commit()
    return {"message": f"Marked {updated} messages as read"}
