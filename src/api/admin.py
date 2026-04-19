import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Header, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database import get_session
from src.models import Driver, DriverStatus, Order, OrderStatus
from src.services.orders import OrderService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin_key(x_admin_key: Annotated[str | None, Header()] = None):
    settings = get_settings()
    if not settings.admin_api_key:
        return  # key not configured — open in dev
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="invalid admin key")


@router.get("/orders")
async def list_orders(
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(le=100)] = 50,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(_require_admin_key),
):
    if status and status not in {s.value for s in OrderStatus}:
        raise HTTPException(status_code=400, detail=f"invalid status '{status}'")
    orders = await OrderService(session).get_all_orders(status=status, limit=limit)
    return [_format_order(o) for o in orders]


@router.get("/orders/{order_id}")
async def get_order(
    order_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(_require_admin_key),
):
    try:
        oid = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid order id")
    order = await OrderService(session).get_order_detail(oid)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    return _format_order(order, detail=True)


@router.post("/orders/{order_id}/retry-dispatch")
async def retry_dispatch(
    order_id: str,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(_require_admin_key),
):
    try:
        oid = UUID(order_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="invalid order id")

    order_service = OrderService(session)
    order = await order_service.get_order_detail(oid)
    if not order:
        raise HTTPException(status_code=404, detail="order not found")
    if order.status not in (OrderStatus.PENDING, OrderStatus.CONFIRMED):
        raise HTTPException(status_code=409, detail=f"order is {order.status.value}, cannot retry dispatch")

    if order.status == OrderStatus.PENDING:
        await order_service.update_status(oid, OrderStatus.CONFIRMED)
        await session.commit()

    settings = get_settings()
    try:
        from arq import create_pool
        from arq.connections import RedisSettings
        import urllib.parse
        parsed = urllib.parse.urlparse(settings.redis_url)
        rs = RedisSettings(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            database=int(parsed.path.lstrip("/") or 0),
            password=parsed.password,
        )
        arq = await create_pool(rs)
        await arq.enqueue_job(
            "dispatch_order",
            order_id=str(order.id),
            shop_phone=order.shop.phone_number if order.shop else "",
            draft={
                "fuel_type": order.fuel_type.value,
                "quantity_liters": float(order.quantity_liters),
                "latitude": None,
                "longitude": None,
            },
        )
        logger.info(f"admin retry-dispatch queued for order {order.order_number}")
        return {"status": "queued", "order_number": order.order_number}
    except Exception as e:
        logger.error(f"admin retry-dispatch failed for {order.order_number}: {e}")
        raise HTTPException(status_code=503, detail=f"failed to enqueue: {e}")


@router.get("/drivers")
async def list_drivers(
    status: Annotated[str | None, Query()] = None,
    session: AsyncSession = Depends(get_session),
    _: None = Depends(_require_admin_key),
):
    if status and status not in {s.value for s in DriverStatus}:
        raise HTTPException(status_code=400, detail=f"invalid status '{status}'")
    stmt = select(Driver).order_by(Driver.name)
    if status:
        stmt = stmt.where(Driver.status == DriverStatus(status))
    result = await session.execute(stmt)
    drivers = result.scalars().all()
    return [
        {
            "id": str(d.id),
            "name": d.name,
            "phone_number": d.phone_number,
            "vehicle_plate": d.vehicle_plate,
            "status": d.status.value,
            "depot_id": str(d.depot_id),
        }
        for d in drivers
    ]


def _format_order(order: Order, detail: bool = False) -> dict:
    data = {
        "id": str(order.id),
        "order_number": order.order_number,
        "status": order.status.value,
        "fuel_type": order.fuel_type.value,
        "quantity_liters": float(order.quantity_liters),
        "delivery_address": order.delivery_address,
        "created_at": order.created_at.isoformat() if order.created_at else None,
        "shop_phone": order.shop.phone_number if order.shop else None,
    }
    if order.assignment:
        a = order.assignment
        data["assignment"] = {
            "status": a.status.value,
            "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            "completed_at": a.completed_at.isoformat() if a.completed_at else None,
            "driver": {
                "name": a.driver.name,
                "phone_number": a.driver.phone_number,
                "vehicle_plate": a.driver.vehicle_plate,
            } if a.driver else None,
        }
    if detail and order.depot:
        data["depot"] = {"id": str(order.depot.id), "name": order.depot.name}
    return data
