from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Campaign(Base):
    __tablename__ = "campaigns"

    id               = Column(Integer, primary_key=True, index=True)
    client_id        = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    template_id      = Column(Integer, ForeignKey("templates.id"), nullable=False)
    name             = Column(String(255), nullable=False)
    target_tags      = Column(ARRAY(String), default=[])        # [] means all contacts
    status           = Column(String(50), default="draft")      # draft/scheduled/running/completed/failed
    scheduled_at     = Column(DateTime, nullable=True)
    started_at       = Column(DateTime, nullable=True)
    completed_at     = Column(DateTime, nullable=True)
    total_contacts   = Column(Integer, default=0)
    sent             = Column(Integer, default=0)
    delivered        = Column(Integer, default=0)
    read             = Column(Integer, default=0)
    failed           = Column(Integer, default=0)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client   = relationship("Client", back_populates="campaigns")
    template = relationship("Template", back_populates="campaigns")
    logs     = relationship("CampaignLog", back_populates="campaign")


class CampaignLog(Base):
    __tablename__ = "campaign_logs"

    id               = Column(Integer, primary_key=True, index=True)
    campaign_id      = Column(Integer, ForeignKey("campaigns.id"), nullable=False, index=True)
    contact_id       = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    status           = Column(String(50), default="queued")     # queued/sent/delivered/read/failed
    meta_message_id  = Column(String(100), nullable=True)       # wamid from Meta
    sent_at          = Column(DateTime, nullable=True)
    delivered_at     = Column(DateTime, nullable=True)
    read_at          = Column(DateTime, nullable=True)
    failed_at        = Column(DateTime, nullable=True)
    error_message    = Column(String(500), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow)

    # Relationships
    campaign = relationship("Campaign", back_populates="logs")
    contact  = relationship("Contact", back_populates="campaign_logs")
