# Design Document: Enhanced Dispatch with Multi-Depot Fallback

## Overview

This feature enhances the dispatch service to search multiple depots when the closest depot has no available drivers. It also adds an owner field to the Depot model for multi-depot ownership support.

## Architecture

### Current Flow

```
Order → Find Nearest Depot → Find Driver at that Depot → Assign or Fail
```

### New Flow

```
Order → Find Nearest Depot (Primary) → Find Driver at Primary Depot
                                        ↓ (no driver)
                                    Find Fallback Depots (ordered by distance from primary)
                                        ↓
                                    For each fallback depot:
                                        Find available driver → Assign
                                        ↓ (no driver)
                                    Continue to next fallback
                                        ↓ (no more depots)
                                    Return no assignment
```

## Components and Interfaces

### Depot Model Changes

Add optional `owner_id` field:

```python
class Depot(Base):
    __tablename__ = "depots"

    id: Mapped[uuid_pk]
    name: Mapped[str_255]
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    location: Mapped[bytes] = mapped_column(Geometry("POINT", srid=4326))
    fuel_types_available: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    owner_id: Mapped[UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)  # NEW
    created_at: Mapped[timestamp_now]
```

### DispatchService Changes

**New Method: `find_fallback_depots`**

```python
async def find_fallback_depots(
    self,
    primary_depot: Depot,
    fuel_type: str,
    max_distance_km: float = 50.0,
) -> list[Depot]:
    """
    Find other depots with the fuel type, ordered by distance from primary depot.
    
    Args:
        primary_depot: The depot we already checked (excluded from results)
        fuel_type: Required fuel type
        max_distance_km: Maximum distance from primary depot
        
    Returns:
        List of depots ordered by distance from primary_depot
    """
```

**Modified Method: `dispatch_order`**

```python
async def dispatch_order(
    self,
    order: Order,
    latitude: float,
    longitude: float,
) -> DispatchResult:
    """
    Dispatch order with multi-depot fallback.
    
    Returns:
        DispatchResult with:
        - depot: The assigned depot (or None)
        - assignment: The delivery assignment (or None)
        - distance_km: Distance from depot to delivery location
        - is_fallback: True if assigned from fallback depot
    """
```

**New Return Type: `DispatchResult`**

```python
@dataclass
class DispatchResult:
    depot: Depot | None
    assignment: DeliveryAssignment | None
    distance_km: float | None
    is_fallback: bool = False
```

### Dispatch Algorithm

```python
async def dispatch_order(self, order, latitude, longitude) -> DispatchResult:
    # 1. Find primary (nearest) depot
    primary_depot = await self.find_nearest_depot(latitude, longitude, order.fuel_type.value)
    
    if not primary_depot:
        return DispatchResult(None, None, None)
    
    # Calculate distance for pricing foundation
    distance_km = await self._calculate_distance(primary_depot, latitude, longitude)
    
    # 2. Try to find driver at primary depot
    driver = await self.find_available_driver(primary_depot.id)
    if driver:
        order.depot_id = primary_depot.id
        assignment = await self.assign_driver(order.id, driver.id)
        return DispatchResult(primary_depot, assignment, distance_km, is_fallback=False)
    
    # 3. Find fallback depots (ordered by distance from primary)
    fallback_depots = await self.find_fallback_depots(primary_depot, order.fuel_type.value)
    
    # 4. Try each fallback depot
    for fallback_depot in fallback_depots:
        driver = await self.find_available_driver(fallback_depot.id)
        if driver:
            fallback_distance = await self._calculate_distance(fallback_depot, latitude, longitude)
            order.depot_id = fallback_depot.id
            assignment = await self.assign_driver(order.id, driver.id)
            return DispatchResult(fallback_depot, assignment, fallback_distance, is_fallback=True)
    
    # 5. No drivers available anywhere
    order.depot_id = primary_depot.id  # Keep primary depot for manual follow-up
    return DispatchResult(primary_depot, None, distance_km, is_fallback=False)
```

## Database Migration

### Add owner_id to Depot

```python
# alembic/versions/YYYYMMDD_add_depot_owner.py
def upgrade() -> None:
    op.add_column('depots', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))

def downgrade() -> None:
    op.drop_column('depots', 'owner_id')
```

## Correctness Properties

### Property 1: Fallback Depot Ordering

For any dispatch where the primary depot has no available drivers, fallback depots SHALL be searched in order of increasing distance from the primary depot location.

### Property 2: Fuel Type Availability

For any depot returned by `find_fallback_depots`, the depot MUST have the requested fuel type in `fuel_types_available`.

### Property 3: Primary Depot Exclusion

The primary depot SHALL NOT appear in the fallback depot list.

## Testing Strategy

### Unit Tests

- Test `find_fallback_depots` returns depots ordered by distance
- Test `find_fallback_depots` excludes primary depot
- Test `find_fallback_depots` filters by fuel type
- Test `dispatch_order` returns fallback result when primary has no driver
- Test `dispatch_order` returns primary result when primary has driver
- Test `dispatch_order` returns no assignment when no drivers anywhere

### Integration Tests

- Test full dispatch flow with multiple depots and drivers
- Test distance calculation accuracy
- Test depot owner assignment