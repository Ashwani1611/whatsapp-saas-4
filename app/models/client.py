from sqlalchemy import Column, Integer, String, Boolean, DateTime, Numeric, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.database import Base


class Client(Base):
    __tablename__ = "clients"

    id                = Column(Integer, primary_key=True, index=True)
    business_name     = Column(String(255), nullable=False)
    email             = Column(String(255), unique=True, nullable=False)
    phone             = Column(String(20), nullable=True)
    custom_domain     = Column(String(255), unique=True, nullable=True)   # whatsapp.skylinebajaj.com
    subdomain         = Column(String(100), unique=True, nullable=True)   # skylinebajaj.yourplatform.com
    plan              = Column(String(50), default="basic")               # free/basic/pro/enterprise
    wallet_balance    = Column(Numeric(10, 4), default=0.0000)
    logo_url          = Column(String(500), nullable=True)
    brand_color       = Column(String(10), nullable=True)                 # white-label color
    is_active         = Column(Boolean, default=True)
    created_at        = Column(DateTime, default=datetime.utcnow)
    updated_at        = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    users        = relationship("User", back_populates="client", cascade="all, delete")
    wa_numbers   = relationship("WANumber", back_populates="client", cascade="all, delete")
    contacts     = relationship("Contact", back_populates="client", cascade="all, delete")
    templates    = relationship("Template", back_populates="client", cascade="all, delete")
    campaigns    = relationship("Campaign", back_populates="client", cascade="all, delete")
    messages     = relationship("Message", back_populates="client", cascade="all, delete")
    transactions = relationship("Transaction", back_populates="client", cascade="all, delete")
    auto_replies = relationship("AutoReply", back_populates="client", cascade="all, delete")
