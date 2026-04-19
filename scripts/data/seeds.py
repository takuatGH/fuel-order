DEPOTS = [
    {
        "name": "FuelFlow Depot Sandton",
        "phone_number": "+27110000001",
        "lat": -26.1076,
        "lng": 28.0567,
        "fuel_types": ["diesel", "petrol", "paraffin"],
        "price_per_liter": 22.50,
    },
    {
        "name": "FuelFlow Depot Midrand",
        "phone_number": "+27110000002",
        "lat": -25.9988,
        "lng": 28.1282,
        "fuel_types": ["diesel", "petrol"],
        "price_per_liter": 21.80,
    },
    {
        "name": "FuelFlow Depot Soweto",
        "phone_number": "+27110000003",
        "lat": -26.2678,
        "lng": 27.8585,
        "fuel_types": ["diesel", "paraffin"],
        "price_per_liter": 21.20,
    },
]

# Each driver entry must reference a depot by exact name from DEPOTS above.
# phone_number must be the full international format without '+' (WhatsApp sends it this way).
DRIVERS = [
    {
        "name": "Test Driver (Takudzwa)",
        "phone_number": "27791885824",
        "vehicle_plate": "TEST 001",
        "depot": "FuelFlow Depot Sandton",
    },
    {
        "name": "Test Driver 2",
        "phone_number": "27799626597",
        "vehicle_plate": "TEST 002",
        "depot": "FuelFlow Depot Sandton",
    },
    {
        "name": "Sipho Nkosi",
        "phone_number": "27711000001",
        "vehicle_plate": "GP 12 AB",
        "depot": "FuelFlow Depot Sandton",
    },
    {
        "name": "Thabo Dlamini",
        "phone_number": "27711000002",
        "vehicle_plate": "GP 34 CD",
        "depot": "FuelFlow Depot Sandton",
    },
    {
        "name": "Lerato Mokoena",
        "phone_number": "27711000003",
        "vehicle_plate": "GP 56 EF",
        "depot": "FuelFlow Depot Midrand",
    },
    {
        "name": "Kagiso Sithole",
        "phone_number": "27711000004",
        "vehicle_plate": "NW 78 GH",
        "depot": "FuelFlow Depot Midrand",
    },
    {
        "name": "Bongani Zulu",
        "phone_number": "27711000005",
        "vehicle_plate": "GP 90 IJ",
        "depot": "FuelFlow Depot Soweto",
    },
]
