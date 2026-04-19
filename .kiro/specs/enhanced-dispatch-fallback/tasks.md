# Implementation Plan: Enhanced Dispatch with Multi-Depot Fallback

## Tasks

- [ ] 1. Add owner_id field to Depot model
  - Add `owner_id: Mapped[UUID | None]` to `src/models/depot.py`
  - Make it nullable (optional field)
  - _Requirements: 2.1, 2.2_

- [ ] 2. Create database migration for depot owner_id
  - Create alembic migration to add owner_id column
  - Migration should be reversible
  - _Requirements: 2.1_

- [ ] 3. Add DispatchResult dataclass to dispatch.py
  - Create dataclass with depot, assignment, distance_km, is_fallback fields
  - _Requirements: 1.3, 3.1, 3.2_

- [ ] 4. Add _calculate_distance helper method
  - Calculate distance between depot location and delivery coordinates
  - Return distance in kilometers
  - _Requirements: 3.1, 3.3_

- [ ] 5. Add find_fallback_depots method
  - Find depots with fuel type, excluding primary depot
  - Order by distance from primary depot location
  - Respect max_distance_km parameter
  - _Requirements: 1.1, 1.2_

- [ ] 6. Modify dispatch_order to implement fallback logic
  - Try primary depot first
  - If no driver, iterate through fallback depots
  - Update order.depot_id to assigned depot
  - Return DispatchResult with distance and fallback flag
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 3.1, 3.2_

- [ ] 7. Checkpoint - Run tests and verify
  - Run existing tests to ensure no regressions
  - Verify dispatch logic works with single depot (backward compatible)

- [ ] 8. Add unit tests for find_fallback_depots
  - Test ordering by distance
  - Test fuel type filtering
  - Test primary depot exclusion
  - Test empty result when no depots match

- [ ] 9. Add unit tests for dispatch_order fallback
  - Test primary depot assignment (no fallback)
  - Test fallback depot assignment
  - Test no assignment when no drivers anywhere
  - Test distance calculation in result

- [ ] 10. Final checkpoint - Ensure all tests pass