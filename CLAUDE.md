# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

**FuelFlow** — a WhatsApp-native B2B fuel delivery platform. Shops order fuel via WhatsApp conversation; drivers accept/deliver jobs; the system dispatches via geospatial nearest-depot + driver availability logic.

## Dev Commands

**Start infrastructure:**
```bash
docker compose -f docker/docker-compose.yml up -d
alembic upgrade head
python scripts/seed_depots.py
python scripts/seed_drivers.py
```

**Run server:**
```bash
uvicorn src.main:app --reload --port 8000
```

**Tests:**
```bash
pytest
pytest --cov=src --cov-report=term-missing
pytest tests/test_conversation/ -v          # run a specific suite
pytest tests/test_services/test_orders.py   # run a single file
```

**Lint / type-check:**
```bash
ruff check src tests
mypy src
```

**Migrations:**
```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
alembic downgrade -1
```

## Architecture

```
WhatsApp Cloud API → POST /webhook → signature validation → message routing
  ├── Shop messages  → MessageHandler → OrderFlow FSM → state stored in Redis
  └── Driver messages → DriverMessageHandler → offer accept/decline/delivery confirm

Order placement → ARQ task queue → dispatch_order task
  ├── DispatchService.find_nearest_depot (PostGIS ST_DWithin)
  ├── DispatchService.find_available_driver
  └── WhatsAppClient sends offer to driver
```

**Key layers:**

| Layer | Path | Purpose |
|---|---|---|
| API / webhook | `src/api/webhooks.py` | Receive & verify WhatsApp webhooks, extract message type, route |
| Shop FSM | `src/conversation/states.py` | Declarative state machine: idle → fuel_type → quantity → location → confirmation → placed |
| Intent parsing | `src/conversation/intents.py` | Rule-based keyword matching (no ML) |
| Message handling | `src/conversation/handlers.py` | Orchestrates shop conversation turn |
| Driver handling | `src/conversation/driver_handlers.py` | Offer accept/decline, delivery confirmation |
| Services | `src/services/` | `orders.py`, `dispatch.py`, `identity.py`, `geocoding.py`, `whatsapp.py` |
| Async tasks | `src/tasks/dispatch.py` | ARQ job: depot lookup → driver selection → offer send (off webhook path) |
| Models | `src/models/` | SQLAlchemy async ORM; Order, Driver, Depot, ShopProfile, DeliveryAssignment |
| Config | `src/config.py` | Pydantic Settings — all tuneable params via env vars |
| DB session | `src/database.py` | Async engine, session factory, FastAPI dependency |

## Data Flow Details

**Shop order flow:** OrderDraft accumulates fields in Redis as the FSM advances; on confirmation an `Order` row is created with status `pending`, then `dispatch_order` task is enqueued via ARQ.

**Driver offer flow:** ARQ task finds nearest depot → nearest available driver → sends interactive WhatsApp buttons → driver reply triggers `DriverMessageHandler` → status transitions via `DeliveryAssignment`.

**Order statuses:** `pending → confirmed → dispatched → delivered / cancelled`

**Driver statuses:** `available → pending_acceptance → on_delivery → offline`

## Critical Design Choices

- **No ML anywhere.** Intent parsing is keyword pattern-matching for speed and testability.
- **Idempotency by Redis key:** Meta re-delivers webhooks; `tasks/idempotency.py` deduplicates by message ID.
- **Everything async:** SQLAlchemy async ORM + AsyncPG + aioredis + httpx throughout. Never use sync DB calls inside async handlers.
- **ARQ, not Celery:** `tasks/celery.py` is an unused stub — ARQ (`tasks/dispatch.py`) is the live task queue.
- **PostGIS for location:** Nearest-depot queries use `ST_DWithin` / `ST_Distance`; Depot model stores `location` as PostGIS geometry.
- **Geocoding cached 24 h:** Nominatim reverse geocoding results are cached in Redis (`GEOCODING_CACHE_TTL_SECONDS`).

## Environment Variables

Copy `.env.example`. Key vars:

| Var | Purpose |
|---|---|
| `DATABASE_URL` | Async Postgres (`postgresql+asyncpg://...`) |
| `REDIS_URL` | Redis connection |
| `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_VERIFY_TOKEN`, `WHATSAPP_WEBHOOK_SECRET` | Meta Cloud API credentials |
| `ENABLE_SIGNATURE_VERIFICATION` | Toggle webhook HMAC validation (disable in local dev) |
| `DRIVER_ACCEPTANCE_TIMEOUT_SECONDS` | Offer expiry window (default 300) |
| `MAX_DRIVER_REASSIGNMENT_ATTEMPTS` | Fallback retries (default 3) |
| `DELIVERY_PROXIMITY_THRESHOLD_M` | Location validation radius in metres (default 500) |
| `ADMIN_WHATSAPP_NUMBER` | Optional admin digest recipient |

## Testing Notes

- Tests use `pytest-asyncio`; fixtures are in `tests/conftest.py`.
- Service tests hit a real test database — do not mock the DB layer.
- Webhook tests use HMAC-signed payloads; see existing test fixtures for the pattern.
