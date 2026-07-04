from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.client import Client

# Routes that don't need tenant identification
PUBLIC_ROUTES = [
    "/api/v1/admin",
    "/api/v1/auth",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/health",
    "/admin",
]


async def tenant_middleware(request: Request, call_next):
    # Skip tenant check for public/admin routes
    path = request.url.path
    if any(path.startswith(route) for route in PUBLIC_ROUTES):
        request.state.client = None
        request.state.client_id = None
        return await call_next(request)

    # Read host from request
    host = request.headers.get("host", "").split(":")[0]  # remove port if present

    # Local development: treat localhost / 127.0.0.1 as the platform domain
    if host in ("localhost", "127.0.0.1"):
        request.state.client = None
        request.state.client_id = None
        return await call_next(request)

    db: Session = SessionLocal()
    try:
        # Find client by custom domain OR subdomain
        client = db.query(Client).filter(
            (Client.custom_domain == host) |
            (Client.subdomain == host.split(".")[0])
        ).filter(Client.is_active == True).first()

        if not client:
            # Check if it's the platform's own domain (for superadmin)
            from app.config import settings
            if settings.PLATFORM_DOMAIN in host:
                request.state.client = None
                request.state.client_id = None
                return await call_next(request)

            return JSONResponse(
                status_code=404,
                content={"detail": "Platform not found for this domain"}
            )

        request.state.client    = client
        request.state.client_id = client.id

    finally:
        db.close()

    return await call_next(request)