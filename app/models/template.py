from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Template(Base):
    __tablename__ = "templates"

    id               = Column(Integer, primary_key=True, index=True)
    client_id        = Column(Integer, ForeignKey("clients.id"), nullable=False, index=True)
    name             = Column(String(255), nullable=False)                        # template_name in Meta
    category         = Column(String(50), nullable=False)                         # marketing/utility/authentication
    language         = Column(String(10), default="en")                           # en, hi, etc
    components       = Column(JSONB, nullable=False)                              # Meta template components JSON
    meta_template_id = Column(String(100), nullable=True)                        # ID returned by Meta after approval
    status           = Column(String(50), default="pending")                     # pending/approved/rejected
    rejection_reason = Column(String(500), nullable=True)
    is_active        = Column(Boolean, default=True)
    created_at       = Column(DateTime, default=datetime.utcnow)
    updated_at       = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    client    = relationship("Client", back_populates="templates")
    campaigns = relationship("Campaign", back_populates="template")
