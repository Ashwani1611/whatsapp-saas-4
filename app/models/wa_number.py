from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class WANumber(Base):
    __tablename__ = "wa_numbers"

    id                   = Column(Integer, primary_key=True, index=True)
    client_id            = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    phone_number_id      = Column(String(100), unique=True, nullable=False)   # Meta's phone number ID
    display_phone_number = Column(String(20), nullable=False)                 # +919876543210
    waba_id              = Column(String(100), nullable=False)                # WhatsApp Business Account ID
    access_token         = Column(Text, nullable=False)                       # encrypted
    webhook_verify_token = Column(String(100), nullable=False)
    status               = Column(String(50), default="pending")              # connected/pending/failed
    is_active            = Column(Boolean, default=True)
    created_at           = Column(DateTime, default=datetime.utcnow)
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client = relationship("Client", back_populates="wa_numbers")
