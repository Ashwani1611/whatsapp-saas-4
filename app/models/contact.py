from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Contact(Base):
    __tablename__ = "contacts"

    id                  = Column(Integer, primary_key=True, index=True)
    client_id           = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    name                = Column(String(255), nullable=False)
    phone               = Column(String(20), nullable=False, index=True)    # +919876543210
    email               = Column(String(255), nullable=True)
    tags                = Column(ARRAY(String), default=[])                  # ["dealer", "hot-lead"]
    custom_attributes   = Column(JSONB, default={})                          # {"city": "Delhi", "model": "Pulsar"}
    opted_in            = Column(Boolean, default=True)                      # WhatsApp opt-in status
    is_active           = Column(Boolean, default=True)
    last_contacted_at   = Column(DateTime, nullable=True)
    created_at          = Column(DateTime, default=datetime.utcnow)
    updated_at          = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client        = relationship("Client", back_populates="contacts")
    messages      = relationship("Message", back_populates="contact")
    campaign_logs = relationship("CampaignLog", back_populates="contact")
