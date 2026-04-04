# usage: python scripts/seed_drivers.py
# idempotent — skips drivers whose phone_number already exists
# drivers and their depot assignments are defined in scripts/data/seeds.py
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.config import get_settings
from src.models import Driver, DriverStatus, Depot
from data.seeds import DRIVERS


async def seed():
    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        for data in DRIVERS:
            existing = await session.execute(
                select(Driver).where(Driver.phone_number == data["phone_number"])
            )
            if existing.scalar_one_or_none():
                print(f"  skip  {data['name']} (already exists)")
                continue

            depot_result = await session.execute(
                select(Depot).where(Depot.name == data["depot"])
            )
            depot = depot_result.scalar_one_or_none()
            if not depot:
                print(f"  error {data['name']}: depot '{data['depot']}' not found — run seed_depots.py first")
                continue

            session.add(Driver(
                depot_id=depot.id,
                phone_number=data["phone_number"],
                name=data["name"],
                vehicle_plate=data["vehicle_plate"],
                status=DriverStatus.AVAILABLE,
            ))
            print(f"  added {data['name']} ({data['phone_number']}) @ {depot.name}")

        await session.commit()

    await engine.dispose()
    print("done.")


if __name__ == "__main__":
    asyncio.run(seed())
