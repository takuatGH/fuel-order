# Implementation Plan: Driver Availability Messaging

## Overview

This implementation adds driver availability signaling via WhatsApp, allowing drivers to mark themselves available or offline. The changes extend the existing IntentParser and DriverMessageHandler with minimal modifications.

## Tasks

- [x] 1. Add availability keyword sets and intents to IntentParser
  - Add `AVAILABILITY_TRIGGERS = {"available", "online", "ready"}` keyword set
  - Add `OFFLINE_TRIGGERS = {"offline", "break", "offduty"}` keyword set
  - _Requirements: 1.1, 2.1, 4.1, 4.2_

- [x] 2. Add availability intent detection to IntentParser._parse_text()
  - Check for availability triggers after help triggers, before cancel triggers
  - Return `ParsedIntent(intent="mark_available")` for availability keywords
  - Return `ParsedIntent(intent="mark_offline")` for offline keywords
  - Ensure availability intents take precedence over state-specific parsing
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ]* 2.1 Write property test for availability keyword detection
  - **Property 1: Availability Keyword Detection**
  - **Validates: Requirements 1.1, 4.1**

- [ ]* 2.2 Write property test for offline keyword detection
  - **Property 2: Offline Keyword Detection**
  - **Validates: Requirements 2.1, 4.2**

- [ ]* 2.3 Write property test for availability intent precedence
  - **Property 3: Availability Intent Precedence**
  - **Validates: Requirements 4.3, 4.4**

- [x] 3. Add response functions to responses.py
  - Add `driver_now_available()` - confirmation when driver marks available
  - Add `driver_already_available()` - when already available
  - Add `driver_now_offline()` - confirmation when driver goes offline
  - Add `driver_already_offline()` - when already offline
  - Add `driver_cannot_change_status_on_delivery()` - rejection for on_delivery state
  - Add `driver_cannot_change_status_pending()` - rejection for pending_acceptance state
  - Add `driver_help_message()` - updated help with availability commands
  - _Requirements: 1.2, 1.3, 2.2, 2.3, 1.4, 1.5, 2.4, 2.5, 5.1-5.5, 6.1-6.3_

- [x] 4. Add _handle_availability() method to DriverMessageHandler
  - Accept driver and intent parameters
  - Check current driver status for transition guards
  - Handle AVAILABLE → mark_available: return already_available message
  - Handle AVAILABLE → mark_offline: transition to OFFLINE, return now_offline
  - Handle OFFLINE → mark_available: transition to AVAILABLE, return now_available
  - Handle OFFLINE → mark_offline: return already_offline message
  - Handle ON_DELIVERY: reject with cannot_change_status_on_delivery
  - Handle PENDING_ACCEPTANCE: reject with cannot_change_status_pending
  - _Requirements: 1.1-1.5, 2.1-2.5_

- [ ]* 4.1 Write property test for status transition guard
  - **Property 4: Status Transition Guard**
  - **Validates: Requirements 1.4, 1.5, 2.4, 2.5**

- [x] 5. Add _track_messaging_window() helper to DriverMessageHandler
  - Set Redis key `driver_window:{phone_number}` with ISO timestamp
  - Set 24-hour TTL (86400 seconds) on the key
  - Handle Redis errors gracefully (best-effort, log warning)
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 6. Modify DriverMessageHandler.handle() to route availability intents
  - Call `_track_messaging_window()` at the start of handle()
  - Parse message with IntentParser
  - Route `mark_available` and `mark_offline` intents to `_handle_availability()`
  - Route `help` intent to return `driver_help_message()`
  - Maintain existing flow for job offers and deliveries
  - _Requirements: 1.1, 2.1, 4.1-4.4, 6.1_

- [ ] 7. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Add unit tests for IntentParser availability intents
  - Test each availability keyword triggers mark_available intent
  - Test each offline keyword triggers mark_offline intent
  - Test keyword matching is case-insensitive
  - Test keywords work as substrings (e.g., "I'm available" → mark_available)
  - Test availability intents work in all driver states
  - _Requirements: 4.1, 4.2, 4.3, 4.4_

- [ ] 9. Add unit tests for DriverMessageHandler availability handling
  - Test status transitions for each starting state (AVAILABLE, OFFLINE, ON_DELIVERY, PENDING_ACCEPTANCE)
  - Test rejection messages for blocked states
  - Test idempotency (already available → already available message)
  - Test messaging window tracking on each message
  - _Requirements: 1.1-1.5, 2.1-2.5, 3.1-3.3_

- [ ] 10. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design
- Unit tests validate specific examples and edge cases