"""seed script - populate database with test depots and drivers.

run with:
    python -m src.scripts.seed
    
or for async:
    python src/scripts/seed.py
"""
import asyncio
import uuid
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.functions import ST_MakePoint

from src.database import get_db_session
from src.models import Depot, Driver, DriverStatus


# sample depots near johannesburg
SAMPLE_DEPOTS = [
    {
        "name": "Sandton Fuel Depot",
        "phone_number": "+27110001001",
        "location": (-26.1076, 28.0567),  # sandton
        "fuel_types_available": ["diesel", "petrol", "paraffin"],
    },
    {
        "name": "Midrand Distribution Hub",
        "phone_number": "+27110001002",
        "location": (-25.9891, 28.1270),  # midrand
        "fuel_types_available": ["diesel", "petrol"],
    },
    {
        "name": "Soweto Fuel Center",
        "phone_number": "+27110001003",
        "location": (-26.2485, 27.8540),  # soweto
        "fuel_types_available": ["diesel", "petrol", "paraffin"],
    },
]

# sample drivers
SAMPLE_DRIVERS = [
    {"name": "Thabo Molefe", "phone_number": "+27821111001", "vehicle_plate": "GP 123 ABC"},
    {"name": "Sipho Ndlovu", "phone_number": "+27821111002", "vehicle_plate": "GP 456 DEF"},
    {"name": "Bongani Mkhize", "phone_number": "+27821111003", "vehicle_plate": "GP 789 GHI"},
    {"name": "Lebo Tau", "phone_number": "+27821111004", "vehicle_plate": "GP 012 JKL"},
]


async def seed_database():
    """populate database with sample data."""
    async with get_db_session() as session:
        print("seeding depots...")
        depots = []
        
        for depot_data in SAMPLE_DEPOTS:
            lat, lng = depot_data["location"]
            depot = Depot(
                id=uuid.uuid4(),
                name=depot_data["name"],
                phone_number=depot_data["phone_number"],
                location=ST_MakePoint(lng, lat, srid=4326),
                fuel_types_available=depot_data["fuel_types_available"],
                is_active=True,
            )
            session.add(depot)
            depots.append(depot)
            print(f"  + {depot.name}")
        
        await session.flush()
        
        print("\nseeding drivers...")
        for i, driver_data in enumerate(SAMPLE_DRIVERS):
            # distribute drivers across depots
            depot = depots[i % len(depots)]
            
            driver = Driver(
                id=uuid.uuid4(),
                depot_id=depot.id,
                name=driver_data["name"],
                phone_number=driver_data["phone_number"],
                vehicle_plate=driver_data["vehicle_plate"],
                status=DriverStatus.AVAILABLE,
            )
            session.add(driver)
            print(f"  + {driver.name} → {depot.name}")
        
        await session.commit()
        print("\n✓ seeding complete!")


async def clear_seed_data():
    """remove all seed data (for testing)."""
    async with get_db_session() as session:
        await session.execute(text("DELETE FROM delivery_assignments"))
        await session.execute(text("DELETE FROM orders"))
        await session.execute(text("DELETE FROM drivers"))
        await session.execute(text("DELETE FROM depots"))
        await session.execute(text("DELETE FROM shop_profiles"))
        await session.commit()
        print("✓ cleared all data")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--clear":
        asyncio.run(clear_seed_data())
    else:
        asyncio.run(seed_database())
