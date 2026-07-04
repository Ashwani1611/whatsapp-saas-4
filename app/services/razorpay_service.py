import razorpay
from app.config import settings


class RazorpayService:
    def __init__(self):
        self.client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_SECRET))

    def create_order(self, amount_rupees: float, receipt: str) -> dict:
        """amount_rupees is in Rupees, Razorpay needs paise"""
        amount_paise = int(amount_rupees * 100)
        order = self.client.order.create({
            "amount":   amount_paise,
            "currency": "INR",
            "receipt":  receipt,
            "payment_capture": 1
        })
        return order

    def verify_payment_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        try:
            self.client.utility.verify_payment_signature({
                "razorpay_order_id":   order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature":  signature
            })
            return True
        except razorpay.errors.SignatureVerificationError:
            return False

    def verify_webhook_signature(self, body: str, signature: str, webhook_secret: str) -> bool:
        try:
            self.client.utility.verify_webhook_signature(body, signature, webhook_secret)
            return True
        except Exception:
            return False
