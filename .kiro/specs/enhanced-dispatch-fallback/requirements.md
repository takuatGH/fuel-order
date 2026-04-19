# Requirements Document: Enhanced Dispatch with Multi-Depot Fallback

## Introduction

The current dispatch system finds the nearest depot with the required fuel type and attempts to assign a driver from that depot only. If no driver is available at the closest depot, the dispatch fails. This feature enhances the dispatch logic to fall back to other nearby depots when the closest depot has no available drivers, and adds support for depot ownership tracking.

## Glossary

- **Primary Depot**: The closest depot to the delivery location that has the required fuel type
- **Fallback Depot**: A secondary depot with the required fuel type, searched in order of distance from the primary depot
- **Depot Owner**: A user or entity that owns one or more depots
- **Dispatch Radius**: Maximum distance (in km) to search for depots
- **Driver Availability**: A driver with status `AVAILABLE` who can accept a delivery

## Requirements

### Requirement 1: Multi-Depot Driver Fallback

**User Story:** As a shop owner, I want my order to be fulfilled even if the closest depot has no available drivers, so that I don't lose sales due to driver unavailability.

#### Acceptance Criteria

1. WHEN the dispatch service finds no available driver at the primary depot, THE system SHALL search for available drivers at other depots with the required fuel type
2. WHEN searching fallback depots, THE system SHALL order depots by distance from the primary depot location (working outward)
3. WHEN an available driver is found at a fallback depot, THE system SHALL assign that driver to the order
4. WHEN no drivers are available at any depot within the dispatch radius, THE system SHALL return no assignment (order remains unassigned)
5. WHEN a driver is assigned from a fallback depot, THE order's depot_id SHALL be updated to the fallback depot

### Requirement 2: Depot Owner Field

**User Story:** As a depot owner with multiple locations, I want my depots linked to my account, so that I can manage all my depots under one identity.

#### Acceptance Criteria

1. THE Depot model SHALL have an optional `owner_id` field
2. WHEN a depot is created without an owner_id, THE system SHALL allow it (owner can be assigned later)
3. WHEN querying depots by owner, THE system SHALL return all depots with matching owner_id

### Requirement 3: Distance-Based Pricing Foundation

**User Story:** As a developer, I want distance calculations available for pricing, so that we can implement distance-based delivery fees in the future.

#### Acceptance Criteria

1. THE dispatch service SHALL calculate and return the distance from depot to delivery location
2. THE dispatch result SHALL include the distance in kilometers
3. THE distance calculation SHALL use the same geospatial logic as the depot search

## Out of Scope

- Actual pricing calculation based on distance (future feature)
- Owner authentication and authorization
- Owner-specific dispatch preferences