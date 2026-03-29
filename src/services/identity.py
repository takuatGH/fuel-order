"""identity service - shop profile lookup and registration.

handles finding or creating shop profiles from phone numbers.
in the order flow, we use this to associate orders with shops.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import ShopProfile, VerificationStatus


logger = logging.getLogger(__name__)


class IdentityService:
    """
    manages shop identity for ordering.
    
    usage:
        service = IdentityService(session)
        shop = await service.get_or_create_shop("+27821234567")
    """
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_shop(self, phone_number: str) -> ShopProfile | None:
        """find shop by phone number."""
        stmt = select(ShopProfile).where(ShopProfile.phone_number == phone_number)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_shop_by_id(self, shop_id: UUID) -> ShopProfile | None:
        """find shop by id."""
        stmt = select(ShopProfile).where(ShopProfile.id == shop_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def get_or_create_shop(
        self,
        phone_number: str,
        business_name: str | None = None,
    ) -> ShopProfile:
        """
        find existing shop or create new one from phone number.
        
        new shops are created with pending verification status.
        business_name defaults to phone number if not provided.
        """
        shop = await self.get_shop(phone_number)
        
        if shop:
            logger.debug(f"found existing shop: {shop.id}")
            return shop
        
        # create new shop profile
        shop = ShopProfile(
            phone_number=phone_number,
            business_name=business_name or f"Shop {phone_number[-4:]}",
            verification_status=VerificationStatus.PENDING,
        )
        
        self.session.add(shop)
        await self.session.flush()  # get id without committing
        
        logger.info(f"created new shop profile: {shop.id}")
        return shop
    
    async def update_shop(
        self,
        shop_id: UUID,
        business_name: str | None = None,
        contact_name: str | None = None,
    ) -> ShopProfile | None:
        """update shop profile details."""
        shop = await self.get_shop_by_id(shop_id)
        
        if not shop:
            return None
        
        if business_name:
            shop.business_name = business_name
        if contact_name:
            shop.contact_name = contact_name
        
        await self.session.flush()
        return shop
