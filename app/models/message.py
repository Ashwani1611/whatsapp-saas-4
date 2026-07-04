from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id              = Column(Integer, primary_key=True, index=True)
    client_id       = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    contact_id      = Column(Integer, ForeignKey("contacts.id"), nullable=False, index=True)
    direction       = Column(String(20), nullable=False)          # inbound / outbound
    message_type    = Column(String(50), nullable=False)          # text/image/document/template/audio/video
    content         = Column(JSONB, nullable=False)               # {"text": "Hello"} or {"url": "...", "caption": "..."}
    meta_message_id = Column(String(100), nullable=True, index=True)  # wamid from Meta
    status          = Column(String(50), default="sent")          # sent/delivered/read/failed
    is_automated    = Column(Boolean, default=False)              # sent by auto-reply/campaign
    is_active       = Column(Boolean, default=True)
    created_at      = Column(DateTime, default=datetime.utcnow, index=True)

    # Relationships
    client  = relationship("Client", back_populates="messages")
    contact = relationship("Contact", back_populates="messages")
