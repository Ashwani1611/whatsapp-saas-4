from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from datetime import datetime
from loguru import logger
from app.database import get_db
from app.config import settings
from app.models.message import Message
from app.models.contact import Contact
from app.models.campaign import CampaignLog
from app.models.wa_number import WANumber

router = APIRouter(prefix="/api/v1/wa", tags=["Webhook"])


# ── Webhook Verification (GET) ────────────────────────────────────────────────
@router.get("/webhook")
def verify_webhook(request: Request):
    mode      = request.query_params.get("hub.mode")
    token     = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == settings.WEBHOOK_VERIFY_TOKEN:
        logger.info("Webhook verified successfully")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Webhook verification failed")


# ── Receive Messages (POST) ───────────────────────────────────────────────────
@router.post("/webhook")
async def receive_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Meta sends all events here:
    - Incoming messages from customers
    - Delivery status updates (sent/delivered/read/failed)
    """
    try:
        body = await request.json()
        logger.info(f"Webhook received: {body}")

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # ── Incoming messages ─────────────────────────────────────
                messages = value.get("messages", [])
                for msg in messages:
                    await handle_incoming_message(msg, value, db)

                # ── Status updates (delivered, read, failed) ──────────────
                statuses = value.get("statuses", [])
                for status_update in statuses:
                    await handle_status_update(status_update, db)

        # Must return 200 quickly — Meta retries if no 200 in 200ms
        return {"status": "ok"}

    except Exception as e:
        logger.error(f"Webhook processing error: {e}")
        return {"status": "ok"}  # Always return 200 to Meta


async def handle_incoming_message(msg: dict, value: dict, db: Session):
    phone_number_id = value.get("metadata", {}).get("phone_number_id")

    # Find which client owns this WA number
    wa_number = db.query(WANumber).filter(
        WANumber.phone_number_id == phone_number_id
    ).first()
    if not wa_number:
        logger.warning(f"Unknown phone_number_id: {phone_number_id}")
        return

    client_id = wa_number.client_id
    from_phone = msg.get("from")
    msg_id     = msg.get("id")
    msg_type   = msg.get("type", "text")
    timestamp  = datetime.utcnow()

    # Find or create contact
    contact = db.query(Contact).filter(
        Contact.client_id == client_id,
        Contact.phone     == from_phone
    ).first()

    if not contact:
        contact_name = value.get("contacts", [{}])[0].get("profile", {}).get("name", from_phone)
        contact = Contact(
            client_id = client_id,
            name      = contact_name,
            phone     = from_phone,
        )
        db.add(contact)
        db.flush()

    # Extract content based on message type
    content = {}
    if msg_type == "text":
        content = {"text": msg.get("text", {}).get("body", "")}
    elif msg_type == "image":
        content = {"media_id": msg.get("image", {}).get("id"), "caption": msg.get("image", {}).get("caption", "")}
    elif msg_type == "document":
        content = {"media_id": msg.get("document", {}).get("id"), "filename": msg.get("document", {}).get("filename", "")}
    else:
        content = {"raw": msg}

    # Save message
    message = Message(
        client_id       = client_id,
        contact_id      = contact.id,
        direction       = "inbound",
        message_type    = msg_type,
        content         = content,
        meta_message_id = msg_id,
        status          = "received",
    )
    db.add(message)
    db.commit()

    logger.info(f"Inbound message saved from {from_phone} for client {client_id}")

    # Trigger auto-reply check (async via Celery)
    from app.tasks.broadcast import check_auto_reply
    check_auto_reply.delay(client_id, contact.id, content.get("text", ""))


async def handle_status_update(status_update: dict, db: Session):
    msg_id = status_update.get("id")
    status = status_update.get("status")  # sent/delivered/read/failed
    ts     = datetime.utcnow()

    # Update message status
    message = db.query(Message).filter(
        Message.meta_message_id == msg_id
    ).first()
    if message:
        message.status = status

    # Update campaign log status
    log = db.query(CampaignLog).filter(
        CampaignLog.meta_message_id == msg_id
    ).first()
    if log:
        log.status = status
        if status == "delivered":
            log.delivered_at = ts
            if log.campaign:
                log.campaign.delivered += 1
        elif status == "read":
            log.read_at = ts
            if log.campaign:
                log.campaign.read += 1
        elif status == "failed":
            log.failed_at     = ts
            log.error_message = str(status_update.get("errors", ""))
            if log.campaign:
                log.campaign.failed += 1

    db.commit()
