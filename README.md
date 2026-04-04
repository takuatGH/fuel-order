# FuelFlow

WhatsApp-native B2B fuel delivery platform. Shops place orders by chatting with a bot, drivers receive and accept jobs via WhatsApp, and an admin sees every completed delivery in real time.

---

## Architecture

```
WhatsApp Cloud API
       │
       ▼
FastAPI webhook  (/webhook POST)
       │
       ├── IdentityService  →  is this a driver's number?
       │
       ├── DriverMessageHandler   (driver phones)
       │       ├── offer accept / decline
       │       ├── reassignment loop (Redis)
       │       └── delivery confirmation (text or location share)
       │
       └── MessageHandler         (shop phones)
               └── OrderFlow FSM
                       idle → fuel type → quantity → location → confirmation → placed

PostgreSQL (PostGIS)   ←→   SQLAlchemy async
Redis                  ←→   session state + driver offer/delivery keys
Nominatim (OSM)              reverse geocoding (24 h Redis cache)
```

---

## Prerequisites

- Python 3.11+
- Docker (for Postgres + Redis)
- Conda environment `fuel-order` (or any venv)
- ngrok static domain (for WhatsApp webhook)
- Meta WhatsApp Cloud API credentials

---

## Quick start

### 1. Services

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 2. Environment

Copy `.env.example` to `.env` and fill in:

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/fuelflow
REDIS_URL=redis://localhost:6379/0

WHATSAPP_PHONE_NUMBER_ID=
WHATSAPP_ACCESS_TOKEN=
WHATSAPP_VERIFY_TOKEN=
WHATSAPP_WEBHOOK_SECRET=

ENABLE_SIGNATURE_VERIFICATION=false   # set true in production

# Optional — admin receives a summary of every completed delivery
ADMIN_WHATSAPP_NUMBER=27821234567
```

### 3. Migrations

```bash
alembic upgrade head
```

### 4. Seed data

```bash
cd scripts
python seed_depots.py
python seed_drivers.py
```

All seed data is defined in `scripts/data/seeds.py`. Edit that file to add real driver phone numbers for live testing.

### 5. Run

```bash
bash start.bat      # Windows
# or
uvicorn src.main:app --reload --port 8000
```

### 6. Expose via ngrok

```bash
ngrok http --domain=your-static-domain.ngrok-free.app 8000
```

Set the webhook URL in the Meta developer portal to:
`https://your-static-domain.ngrok-free.app/webhook`

---

## Order flow (shop side)

```
Shop sends "order"
  → chooses fuel type  (interactive buttons: Diesel / Petrol / Paraffin)
  → enters quantity    (10 – 10,000 L)
  → shares location    (native WhatsApp location)
  → confirms summary   (Confirm / Cancel)
  → receives order number + "we'll notify you when a driver accepts"
```

Reverse geocoding via Nominatim turns the GPS pin into a human-readable address shown in the confirmation summary.

## Dispatch flow (driver side)

```
Order confirmed
  → nearest depot found via PostGIS (ST_DWithin, metres)
  → first AVAILABLE driver at that depot receives a WhatsApp job offer
     with Accept / Decline buttons (offer expires after 5 minutes)

Driver accepts
  → shop notified "Driver X (plate) is on the way"
  → driver receives address + delivery instructions

Driver declines (or offer times out)
  → next AVAILABLE driver at same depot offered
  → after max attempts (default 3): shop notified "no drivers available"

Driver confirms delivery
  → type "delivered" / "done" / "complete"
  → or share location (validated within 500 m of delivery point)
  → shop notified "order delivered"
  → admin digest sent (if ADMIN_WHATSAPP_NUMBER configured)
  → driver status returns to AVAILABLE
```

---

## Project structure

```
src/
  api/
    webhooks.py          # WhatsApp webhook: verification + message routing
  conversation/
    states.py            # OrderFlow FSM (declarative transition table)
    intents.py           # Rule-based intent parser
    responses.py         # All outbound message factories (WhatsApp constraints enforced)
    handlers.py          # MessageHandler — shop conversation orchestration
    driver_handlers.py   # DriverMessageHandler — driver offer + delivery flow
  models/
    depot.py             # Depot (PostGIS location, fuel_types_available)
    driver.py            # Driver (status: available / pending_acceptance / on_delivery / offline)
    order.py             # Order + DeliveryAssignment
    shop.py              # ShopProfile
  services/
    dispatch.py          # find_nearest_depot (PostGIS), find_available_driver
    geocoding.py         # Nominatim reverse geocoder with Redis cache
    identity.py          # IdentityService — shop + driver lookup
    orders.py            # OrderService — create, status transitions
    whatsapp.py          # WhatsAppClient — Cloud API wrapper
  config.py              # Pydantic settings (env vars)
  database.py            # Async SQLAlchemy session

scripts/
  data/seeds.py          # Depot + driver seed data (edit here)
  seed_depots.py
  seed_drivers.py

alembic/versions/        # Database migrations
tests/
  test_conversation/
    test_states.py       # OrderFlow FSM unit tests
    test_intents.py      # Intent parser unit tests
    test_responses.py    # Response factory unit tests (incl. WA constraints)
    test_driver_responses.py   # Driver/shop/admin response tests
    test_driver_handlers.py    # DriverMessageHandler unit tests
```

---

## Running tests

```bash
pytest
```

With coverage:

```bash
pytest --cov=src --cov-report=term-missing
```

---

## Configuration reference

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Async Postgres connection string |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection string |
| `WHATSAPP_PHONE_NUMBER_ID` | — | Meta phone number ID |
| `WHATSAPP_ACCESS_TOKEN` | — | Meta system user token |
| `WHATSAPP_VERIFY_TOKEN` | — | Webhook verification token |
| `WHATSAPP_WEBHOOK_SECRET` | — | HMAC signature secret |
| `ENABLE_SIGNATURE_VERIFICATION` | `true` | Set `false` for local dev |
| `ADMIN_WHATSAPP_NUMBER` | `None` | Receives completed-order digest (no `+`) |
| `DRIVER_ACCEPTANCE_TIMEOUT_SECONDS` | `300` | Offer TTL (5 min) |
| `MAX_DRIVER_REASSIGNMENT_ATTEMPTS` | `3` | Decline retries before notifying shop |
| `DELIVERY_PROXIMITY_THRESHOLD_M` | `500` | Location validation radius |
| `GEOCODING_CACHE_TTL_SECONDS` | `86400` | Nominatim result cache (24 h) |

---

## Adding drivers

Edit `scripts/data/seeds.py`:

```python
DRIVERS = [
    {
        "name": "Your Driver",
        "phone_number": "27821234567",   # international format, no +
        "vehicle_plate": "GP 00 AA",
        "depot": "FuelFlow Depot Sandton",  # must match a depot name exactly
    },
    ...
]
```

Then re-run `python scripts/seed_drivers.py` — it is idempotent and skips existing entries.

---

## Database migrations

Create a new migration:

```bash
alembic revision --autogenerate -m "description"
alembic upgrade head
```

Rollback one step:

```bash
alembic downgrade -1
```
