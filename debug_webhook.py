import asyncio
import logging
import os
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/fuelflow")

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s %(message)s")

from fastapi.testclient import TestClient
from src.main import app

payload = {
    "object": "whatsapp_business_account",
    "entry": [{"id": "123", "changes": [{"value": {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "27833050044", "phone_number_id": "984406351433212"},
        "contacts": [{"profile": {"name": "Test"}, "wa_id": "27799626597"}],
        "messages": [{"from": "27799626597", "id": "wamid.test123", "timestamp": "1775306993",
                      "text": {"body": "Hi"}, "type": "text"}]
    }, "field": "messages"}]}]
}

with TestClient(app, raise_server_exceptions=True) as client:
    try:
        r = client.post("/webhook", json=payload)
        print("Status:", r.status_code)
        print("Body:", r.text)
    except Exception as e:
        import traceback
        traceback.print_exc()
