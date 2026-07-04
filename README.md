# WhatsApp SaaS Platform

Multi-tenant WhatsApp Business API SaaS platform — self-hosted alternative to AiSensy/Wati.

## ✅ What's Built (Phase 1 — MVP)

- Multi-tenant architecture (custom domain / subdomain per client)
- JWT auth with 3 roles: superadmin, client_admin, agent
- WhatsApp Cloud API integration (send text/image/document/template)
- Webhook receiver (incoming messages + delivery status)
- Contact management + CSV import
- Template manager (create, submit to Meta, sync approval status)
- Broadcast campaigns (Celery async, rate-limited to 80 msg/sec)
- Campaign analytics (sent/delivered/read/failed)
- Team inbox (conversations, reply, mark resolved)
- Auto-reply engine (welcome message, keyword triggers, fallback)
- WCC wallet system (India rates: ₹0.8631 marketing, ₹0.115 utility/auth)
- Razorpay billing (wallet top-up + verification)
- Superadmin panel (manage clients, manual top-up, platform stats)

## 🚀 Local Setup

### 1. Prerequisites
- Docker + Docker Compose installed
- A Meta Business Account with WhatsApp Cloud API access
- A Razorpay account (test mode is fine to start)

### 2. Clone & Configure
```bash
cp .env.example .env
# Edit .env and fill in:
#   SECRET_KEY (any random 32+ char string)
#   META_APP_ID, META_APP_SECRET (from Meta App Dashboard)
#   WEBHOOK_VERIFY_TOKEN (any string you choose, use same in Meta webhook config)
#   RAZORPAY_KEY_ID, RAZORPAY_SECRET (from Razorpay Dashboard)
#   ENCRYPTION_KEY (any random 32 char string)
#   SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD (your login for admin panel)
```

### 3. Start Everything
```bash
docker compose up --build
```

This starts: FastAPI (port 8000), Celery worker, Celery beat, PostgreSQL, Redis, Nginx (port 80).

### 4. Verify It's Running
```bash
curl http://localhost:8000/health
# {"status":"ok","app":"WhatsApp SaaS Platform","version":"1.0.0"}
```

Visit `http://localhost:8000/docs` for interactive Swagger API docs.

### 5. First Login (Superadmin)
The superadmin user is auto-created on first boot using `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` from `.env`.

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@yourplatform.com","password":"changeme123"}'
```

## 📦 Onboarding Your First Client (e.g. Skyline Bajaj)

1. **Login as superadmin**, get access token
2. **Create the client:**
```bash
curl -X POST http://localhost:8000/api/v1/admin/clients \
  -H "Authorization: Bearer <superadmin_token>" \
  -H "Content-Type: application/json" \
  -d '{
    "business_name": "Skyline Bajaj",
    "email": "owner@skylinebajaj.com",
    "custom_domain": "whatsapp.skylinebajaj.com",
    "plan": "pro",
    "admin_name": "Skyline Admin",
    "admin_password": "SecurePass123"
  }'
```
3. **Client points their domain** — they add this DNS record at their registrar:
```
Type: CNAME
Name: whatsapp
Value: yourplatform.com
```
4. **Client logs in** at `whatsapp.skylinebajaj.com` with the email/password you set
5. **Client connects their WhatsApp number** via `/api/v1/wa-numbers/onboard` (needs phone_number_id, waba_id, access_token from their Meta Business Manager)
6. **Set up Meta webhook** — in Meta App Dashboard, set webhook URL to `https://yourplatform.com/api/v1/wa/webhook` and verify token to match your `.env` `WEBHOOK_VERIFY_TOKEN`

## 🌐 Production Deployment (Railway)

1. Push this code to a GitHub repo
2. Create new Railway project → deploy from GitHub
3. Add PostgreSQL + Redis plugins in Railway (auto-sets DATABASE_URL, REDIS_URL)
4. Add all other env vars from `.env.example` in Railway's Variables tab
5. Add a second Railway service for the Celery worker: same repo, custom start command `celery -A app.tasks.celery_app worker --loglevel=info`
6. Point your domain's DNS (or client's CNAME) to the Railway-provided domain
7. Enable Cloudflare in front for free SSL + wildcard subdomain support

## 📁 Project Structure
```
app/
├── main.py                 # FastAPI entrypoint
├── config.py                # Settings from .env
├── database.py               # SQLAlchemy engine/session
├── middleware/tenant.py       # Multi-tenant domain resolver
├── models/                    # All DB tables
├── routers/                   # All API endpoints
├── services/                  # WhatsApp + Razorpay API wrappers
├── tasks/                      # Celery background jobs
└── utils/                       # Auth, encryption helpers
```

## 🔜 Not Yet Built (Phase 2/3 — build after first paying client)
- No-code chatbot flow builder
- Tally ERP integration
- WhatsApp Flows support
- White-label branding on dashboard frontend
- Multi-agent conversation assignment UI
- Audience segmentation / retargeting UI
- Frontend dashboard (currently API-only — build React/HTML next)

## ⚠️ Before Going Live
- [ ] Change `SECRET_KEY` and `ENCRYPTION_KEY` to strong random values
- [ ] Set `DEBUG=False` in production `.env`
- [ ] Switch Razorpay to live mode keys
- [ ] Set up automated PostgreSQL backups
- [ ] Add rate limiting on public endpoints (slowapi is already in requirements.txt)
- [ ] Test webhook responds under 200ms (Meta requirement)
