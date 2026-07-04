from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # App
    APP_NAME: str = "WhatsApp SaaS Platform"
    SECRET_KEY: str
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "whatsapp_saas"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    CELERY_BROKER_URL: str = "redis://redis:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://redis:6379/0"

    # Meta WhatsApp
    META_APP_ID: str
    META_APP_SECRET: str
    META_API_VERSION: str = "v19.0"
    META_BASE_URL: str = "https://graph.facebook.com"
    WEBHOOK_VERIFY_TOKEN: str

    # Razorpay
    RAZORPAY_KEY_ID: str
    RAZORPAY_SECRET: str

    # Encryption
    ENCRYPTION_KEY: str

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None

    # Platform
    PLATFORM_DOMAIN: str = "yourplatform.com"
    SUPERADMIN_EMAIL: str
    SUPERADMIN_PASSWORD: str

    # JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    class Config:
        env_file = ".env"


settings = Settings()
