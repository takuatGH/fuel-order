import logging

import httpx
import redis.asyncio as redis


logger = logging.getLogger(__name__)


class GeocodingService:
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
    CACHE_PREFIX = "geocode"

    def __init__(self, redis_client: redis.Redis, cache_ttl: int = 86400):
        self.redis = redis_client
        self.cache_ttl = cache_ttl

    async def reverse_geocode(self, lat: float, lng: float) -> str:
        key = f"{self.CACHE_PREFIX}:{lat:.4f}:{lng:.4f}"

        cached = await self.redis.get(key)
        if cached:
            logger.debug(f"geocode cache hit: {key}")
            return cached.decode()

        address = await self._fetch(lat, lng)
        await self.redis.setex(key, self.cache_ttl, address)
        return address

    async def _fetch(self, lat: float, lng: float) -> str:
        try:
            async with httpx.AsyncClient(
                headers={"User-Agent": "FuelFlow/0.1"},
                timeout=3.0,
            ) as client:
                resp = await client.get(
                    self.NOMINATIM_URL,
                    params={"format": "json", "lat": lat, "lon": lng},
                )
                resp.raise_for_status()
                data = resp.json()
                address = data.get("display_name")
                if address:
                    logger.info(f"geocoded ({lat:.4f}, {lng:.4f}) → {address[:60]}")
                    return address
        except Exception as e:
            logger.warning(f"geocoding failed for ({lat:.4f}, {lng:.4f}): {e}")

        return f"{lat:.4f}, {lng:.4f}"
