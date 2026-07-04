from app.tasks.celery_app import celery_app
from app.database import SessionLocal
from loguru import logger


@celery_app.task
def sync_all_pending_templates():
    """Runs every 30 min via Celery beat - syncs template approval status from Meta for all clients"""
    from app.models.template import Template
    from app.models.wa_number import WANumber
    from app.utils.encryption import decrypt
    from app.services.whatsapp import WhatsAppService

    db = SessionLocal()
    try:
        pending = db.query(Template).filter(
            Template.status    == "pending",
            Template.is_active == True
        ).all()

        # Group by client to avoid repeated WA number lookups
        client_ids = {t.client_id for t in pending}
        wa_numbers = {
            w.client_id: w for w in db.query(WANumber).filter(
                WANumber.client_id.in_(client_ids),
                WANumber.status == "connected",
                WANumber.is_active == True
            ).all()
        }

        updated = 0
        for template in pending:
            wa_number = wa_numbers.get(template.client_id)
            if not wa_number:
                continue
            try:
                access_token = decrypt(wa_number.access_token)
                wa_service   = WhatsAppService(wa_number.phone_number_id, access_token)
                result = wa_service.get_template_status(wa_number.waba_id, template.name)
                data = result.get("data", [])
                if data:
                    meta_status = data[0].get("status", "").lower()
                    if meta_status in ["approved", "rejected"]:
                        template.status = meta_status
                        template.rejection_reason = data[0].get("rejected_reason")
                        updated += 1
            except Exception as e:
                logger.error(f"Failed to sync template {template.id}: {e}")
                continue

        db.commit()
        logger.info(f"Synced {updated} templates across {len(client_ids)} clients")

    finally:
        db.close()
