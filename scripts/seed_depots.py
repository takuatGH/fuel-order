# usage: python scripts/seed_depots.py
# idempotent — skips depots whose phone_number already exists
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from geoalchemy2.functions import ST_SetSRID, ST_MakePoint

from src.config import get_settings
from src.models import Depot
from data.seeds import DEPOTS


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for data in DEPOTS:
            existing = await session.execute(
                select(Depot).where(Depot.phone_number == data["phone_number"])
            )
            if existing.scalar_one_or_none():
                print(f"  skip  {data['name']} (already exists)")
                continue

            session.add(Depot(
                name=data["name"],
                phone_number=data["phone_number"],
                location=ST_SetSRID(ST_MakePoint(data["lng"], data["lat"]), 4326),
                fuel_types_available=data["fuel_types"],
                is_active=True,
                price_per_liter=data.get("price_per_liter"),
            ))
            print(f"  added {data['name']} @ ({data['lat']}, {data['lng']})")

        await session.commit()

    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(seed())
