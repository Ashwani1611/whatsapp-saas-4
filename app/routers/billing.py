from fastapi import APIRouter, Depends, HTTPException, Request, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal

from app.database import get_db
from app.models.client import Client
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.auth import require_client_admin
from app.services.razorpay_service import RazorpayService
from app.config import settings

router = APIRouter(prefix="/api/v1/billing", tags=["Billing"])


# ── Schemas ───────────────────────────────────────────────────────────────────
class TopupRequest(BaseModel):
    amount: float   # in rupees, minimum 100


class VerifyPaymentRequest(BaseModel):
    razorpay_order_id:   str
    razorpay_payment_id: str
    razorpay_signature:  str
    amount:              float


# ── Get wallet balance ────────────────────────────────────────────────────────
@router.get("/wallet")
def get_wallet(
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    client = db.query(Client).filter(Client.id == current_user.client_id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")

    return {
        "wallet_balance": float(client.wallet_balance),
        "plan":            client.plan
    }


# ── Create Razorpay order for topup ──────────────────────────────────────────
@router.post("/wallet/topup")
def create_topup_order(
    payload: TopupRequest,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    if payload.amount < 100:
        raise HTTPException(status_code=400, detail="Minimum top-up amount is ₹100")

    razorpay_service = RazorpayService()
    receipt = f"topup_{current_user.client_id}_{int(datetime.utcnow().timestamp())}"

    order = razorpay_service.create_order(payload.amount, receipt)

    return {
        "order_id":  order["id"],
        "amount":    payload.amount,
        "currency":  "INR",
        "key_id":    settings.RAZORPAY_KEY_ID,
    }


# ── Verify payment and credit wallet ─────────────────────────────────────────
@router.post("/wallet/verify")
def verify_topup_payment(
    payload: VerifyPaymentRequest,
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    razorpay_service = RazorpayService()

    is_valid = razorpay_service.verify_payment_signature(
        payload.razorpay_order_id,
        payload.razorpay_payment_id,
        payload.razorpay_signature
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    client = db.query(Client).filter(Client.id == current_user.client_id).first()
    amount = Decimal(str(payload.amount))

    client.wallet_balance += amount

    txn = Transaction(
        client_id           = client.id,
        amount              = amount,
        type                = "topup",
        description         = "Wallet top-up via Razorpay",
        razorpay_payment_id = payload.razorpay_payment_id,
        balance_after       = client.wallet_balance
    )
    db.add(txn)
    db.commit()

    return {
        "message":        "Wallet topped up successfully",
        "wallet_balance": float(client.wallet_balance)
    }


# ── Transaction history ───────────────────────────────────────────────────────
@router.get("/transactions")
def get_transactions(
    page:  int = Query(1, ge=1),
    limit: int = Query(20, le=100),
    type:  Optional[str] = None,   # topup / deduction / refund
    current_user: User = Depends(require_client_admin),
    db: Session        = Depends(get_db)
):
    query = db.query(Transaction).filter(Transaction.client_id == current_user.client_id)
    if type:
        query = query.filter(Transaction.type == type)

    total = query.count()
    txns  = query.order_by(Transaction.created_at.desc()) \
                 .offset((page - 1) * limit).limit(limit).all()

    return {
        "total": total,
        "transactions": [
            {
                "id":            t.id,
                "amount":        float(t.amount),
                "type":          t.type,
                "description":   t.description,
                "balance_after": float(t.balance_after),
                "created_at":    t.created_at,
            }
            for t in txns
        ]
    }


# ── Razorpay webhook (backup payment confirmation) ────────────────────────────
@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    body      = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    razorpay_service = RazorpayService()
    is_valid = razorpay_service.verify_webhook_signature(
        body.decode(), signature, settings.RAZORPAY_SECRET
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    import json
    data  = json.loads(body)
    event = data.get("event")

    if event == "payment.captured":
        payment = data["payload"]["payment"]["entity"]
        receipt = payment.get("notes", {}).get("receipt", "")
        # Extra safety net - main crediting happens in /wallet/verify
        # This just logs/handles cases where frontend verify call failed

    return {"status": "ok"}
