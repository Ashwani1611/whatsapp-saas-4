from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Numeric
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Transaction(Base):
    __tablename__ = "transactions"

    id                  = Column(Integer, primary_key=True, index=True)
    client_id           = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    amount              = Column(Numeric(10, 4), nullable=False)        # positive=topup, negative=deduction
    type                = Column(String(50), nullable=False)            # topup/deduction/refund
    description         = Column(String(500), nullable=True)
    razorpay_payment_id = Column(String(100), nullable=True)
    balance_after       = Column(Numeric(10, 4), nullable=False)
    created_at          = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    client = relationship("Client", back_populates="transactions")


class AutoReply(Base):
    __tablename__ = "auto_replies"

    id               = Column(Integer, primary_key=True, index=True)
    client_id        = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    trigger_type     = Column(String(50), nullable=False)       # keyword/welcome/fallback
    keyword          = Column(String(255), nullable=True)       # only for keyword triggers
    response_type    = Column(String(50), nullable=False)       # text/template
    response_content = Column(JSONB, nullable=False)            # {"text": "..."} or {"template_id": 1}
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = relationship("Client", back_populates="auto_replies")
