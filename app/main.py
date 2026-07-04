from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from loguru import logger

from app.config import settings
from app.database import engine, SessionLocal
from app.models import *  # noqa - registers all models with Base
from app.database import Base
from app.middleware.tenant import tenant_middleware
from app.routers import auth, contacts, templates, campaigns, inbox, billing, webhook, admin, wa_numbers



# ── Startup / Shutdown ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WhatsApp SaaS Platform...")

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables ready")

    # Create superadmin if not exists
    create_superadmin()

    yield
    logger.info("Shutting down...")


def create_superadmin():
    from app.models.user import User, UserRole
    from app.utils.auth import hash_password

    db = SessionLocal()
    try:
        exists = db.query(User).filter(
            User.email == settings.SUPERADMIN_EMAIL
        ).first()

        if not exists:
            superadmin = User(
                name          = "Super Admin",
                email         = settings.SUPERADMIN_EMAIL,
                password_hash = hash_password(settings.SUPERADMIN_PASSWORD),
                role          = UserRole.superadmin,
                client_id     = None
            )
            db.add(superadmin)
            db.commit()
            logger.info(f"Superadmin created: {settings.SUPERADMIN_EMAIL}")
        else:
            logger.info("Superadmin already exists")
    finally:
        db.close()


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title       = settings.APP_NAME,
    description = "Multi-tenant WhatsApp Business SaaS Platform",
    version     = "1.0.0",
    lifespan    = lifespan,
    docs_url    = "/docs" if settings.DEBUG else None,
    redoc_url   = "/redoc" if settings.DEBUG else None,
)


# ── Middleware ────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins     = ["*"],
    allow_credentials = True,
    allow_methods     = ["*"],
    allow_headers     = ["*"],
)

app.middleware("http")(tenant_middleware)


# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(contacts.router)
app.include_router(templates.router)
app.include_router(campaigns.router)
app.include_router(inbox.router)
app.include_router(billing.router)
app.include_router(webhook.router)
app.include_router(admin.router)
app.include_router(wa_numbers.router)


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status":  "ok",
        "app":     settings.APP_NAME,
        "version": "1.0.0"
    }


# ── Static files (frontend dashboard) ─────────────────────────────────────────
try:
    app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
except Exception:
    pass


@app.get("/")
def serve_dashboard():
    """Serves the client dashboard SPA at the root of every client domain"""
    from fastapi.responses import FileResponse
    return FileResponse("frontend/dashboard.html")

@app.get("/admin")
def serve_admin_console():
    """Serves the superadmin platform console — manage clients, top-ups, stats"""
    from fastapi.responses import FileResponse
    return FileResponse("frontend/admin.html")