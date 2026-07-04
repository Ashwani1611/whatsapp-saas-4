import time
from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from app.models.campaign import Campaign, CampaignLog
from app.models.contact import Contact
from app.models.wa_number import WANumber
from datetime import datetime
from loguru import logger


@celery_app.task(bind=True, max_retries=3)
def send_broadcast_campaign(self, campaign_id: int):
    db = SessionLocal()
    try:
        campaign = db.query(Campaign).filter(Campaign.id == campaign_id).first()
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found")
            return

        # Mark campaign as running
        campaign.status     = "running"
        campaign.started_at = datetime.utcnow()
        db.commit()

        # Get WA number for this client
        wa_number = db.query(WANumber).filter(
            WANumber.client_id == campaign.client_id,
            WANumber.status    == "connected",
            WANumber.is_active == True
        ).first()

        if not wa_number:
            campaign.status = "failed"
            db.commit()
            logger.error(f"No connected WA number for client {campaign.client_id}")
            return

        # Get contacts based on target_tags
        query = db.query(Contact).filter(
            Contact.client_id == campaign.client_id,
            Contact.opted_in  == True,
            Contact.is_active == True
        )
        if campaign.target_tags:
            query = query.filter(Contact.tags.overlap(campaign.target_tags))

        contacts = query.all()
        campaign.total_contacts = len(contacts)
        db.commit()

        # Send messages with rate limiting (80 msg/sec Meta limit)
        from app.services.whatsapp import WhatsAppService
        from app.utils.encryption import decrypt

        access_token = decrypt(wa_number.access_token)
        wa_service   = WhatsAppService(
            phone_number_id = wa_number.phone_number_id,
            access_token    = access_token
        )

        for i, contact in enumerate(contacts):
            try:
                # Send template message
                result = wa_service.send_template(
                    to          = contact.phone,
                    template_id = campaign.template_id,
                    db          = db
                )

                # Log success
                log = db.query(CampaignLog).filter(
                    CampaignLog.campaign_id == campaign_id,
                    CampaignLog.contact_id  == contact.id
                ).first()

                if log:
                    log.status          = "sent"
                    log.meta_message_id = result.get("messages", [{}])[0].get("id")
                    log.sent_at         = datetime.utcnow()
                else:
                    log = CampaignLog(
                        campaign_id     = campaign_id,
                        contact_id      = contact.id,
                        status          = "sent",
                        meta_message_id = result.get("messages", [{}])[0].get("id"),
                        sent_at         = datetime.utcnow()
                    )
                    db.add(log)

                campaign.sent += 1

                # Deduct wallet for this message
                deduct_wallet_for_message.delay(campaign.client_id, campaign.template.category)

                # Update last contacted
                contact.last_contacted_at = datetime.utcnow()

            except Exception as e:
                logger.error(f"Failed to send to {contact.phone}: {e}")
                log = CampaignLog(
                    campaign_id   = campaign_id,
                    contact_id    = contact.id,
                    status        = "failed",
                    failed_at     = datetime.utcnow(),
                    error_message = str(e)[:500]
                )
                db.add(log)
                campaign.failed += 1

            db.commit()

            # Rate limiting: 80 messages/second max
            if (i + 1) % 80 == 0:
                time.sleep(1)

        # Mark campaign as completed
        campaign.status       = "completed"
        campaign.completed_at = datetime.utcnow()
        db.commit()

        logger.info(f"Campaign {campaign_id} completed: {campaign.sent} sent, {campaign.failed} failed")

    except Exception as e:
        logger.error(f"Campaign {campaign_id} failed: {e}")
        if campaign:
            campaign.status = "failed"
            db.commit()
        raise self.retry(exc=e, countdown=60)
    finally:
        db.close()


@celery_app.task
def check_auto_reply(client_id: int, contact_id: int, incoming_text: str):
    """Check if any auto-reply rule matches and send response"""
    from app.models.transaction import AutoReply
    from app.models.contact import Contact
    from app.models.wa_number import WANumber
    from app.models.message import Message
    from app.utils.encryption import decrypt
    from app.services.whatsapp import WhatsAppService

    db = SessionLocal()
    try:
        client_id_int = client_id

        # Is this the first ever message from this contact? -> welcome trigger
        message_count = db.query(Message).filter(
            Message.client_id  == client_id_int,
            Message.contact_id == contact_id,
            Message.direction  == "inbound"
        ).count()

        rule = None
        text_lower = (incoming_text or "").lower().strip()

        if message_count <= 1:
            rule = db.query(AutoReply).filter(
                AutoReply.client_id    == client_id_int,
                AutoReply.trigger_type == "welcome",
                AutoReply.is_active    == True
            ).first()

        if not rule and text_lower:
            keyword_rules = db.query(AutoReply).filter(
                AutoReply.client_id    == client_id_int,
                AutoReply.trigger_type == "keyword",
                AutoReply.is_active    == True
            ).all()
            for kr in keyword_rules:
                if kr.keyword and kr.keyword.lower() in text_lower:
                    rule = kr
                    break

        if not rule:
            rule = db.query(AutoReply).filter(
                AutoReply.client_id    == client_id_int,
                AutoReply.trigger_type == "fallback",
                AutoReply.is_active    == True
            ).first()

        if not rule:
            return  # no matching rule, do nothing

        wa_number = db.query(WANumber).filter(
            WANumber.client_id == client_id_int,
            WANumber.status    == "connected",
            WANumber.is_active == True
        ).first()
        if not wa_number:
            return

        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        if not contact:
            return

        access_token = decrypt(wa_number.access_token)
        wa_service   = WhatsAppService(wa_number.phone_number_id, access_token)

        if rule.response_type == "text":
            reply_text = rule.response_content.get("text", "")
            result = wa_service.send_text(contact.phone, reply_text)
            content = {"text": reply_text}
        else:
            template_id = rule.response_content.get("template_id")
            result = wa_service.send_template(contact.phone, template_id, db)
            content = {"template_id": template_id}

        message = Message(
            client_id       = client_id_int,
            contact_id      = contact_id,
            direction       = "outbound",
            message_type    = rule.response_type,
            content         = content,
            meta_message_id = result.get("messages", [{}])[0].get("id"),
            status          = "sent",
            is_automated    = True,
        )
        db.add(message)
        db.commit()

    except Exception as e:
        logger.error(f"Auto-reply failed for client {client_id}, contact {contact_id}: {e}")
    finally:
        db.close()


@celery_app.task
def deduct_wallet_for_message(client_id: int, category: str):

    """Deduct WCC from client wallet per message sent"""
    from app.models.client import Client
    from app.models.transaction import Transaction
    from decimal import Decimal

    # India rates (2026)
    RATES = {
        "marketing":      Decimal("0.8631"),
        "utility":        Decimal("0.1150"),
        "authentication": Decimal("0.1150"),
        "service":        Decimal("0.0000"),
    }

    rate = RATES.get(category, Decimal("0.8631"))
    if rate == 0:
        return

    db = SessionLocal()
    try:
        client = db.query(Client).filter(Client.id == client_id).first()
        if not client:
            return

        client.wallet_balance -= rate

        txn = Transaction(
            client_id     = client_id,
            amount        = -rate,
            type          = "deduction",
            description   = f"WhatsApp {category} message charge",
            balance_after = client.wallet_balance
        )
        db.add(txn)
        db.commit()

        # Low balance alert
        if client.wallet_balance < 50:
            logger.warning(f"Client {client_id} low wallet balance: {client.wallet_balance}")

    finally:
        db.close()
