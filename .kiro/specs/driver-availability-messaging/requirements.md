# Requirements Document

## Introduction

This feature enables drivers to proactively signal their availability via WhatsApp, leveraging the 24-hour messaging window to enable free-form communication between the system and drivers. Currently, drivers are passively assigned jobs based on database status with no way to indicate readiness. This creates inefficiencies and prevents the system from utilizing the WhatsApp messaging window effectively.

## Glossary

- **Driver**: A fuel delivery driver registered in the FuelFlow system
- **DriverStatus**: Enum representing driver state (AVAILABLE, ON_DELIVERY, OFFLINE, PENDING_ACCEPTANCE)
- **Availability_Window**: The 24-hour WhatsApp messaging window that opens when a user sends a message, during which the business can send free-form messages without template approval
- **Intent_Parser**: Component that parses WhatsApp messages into structured intents
- **Driver_Message_Handler**: Component that processes driver messages and manages driver state transitions
- **WhatsApp_Client**: Service for sending messages via WhatsApp Cloud API

## Requirements

### Requirement 1: Mark Driver Available

**User Story:** As a driver, I want to signal that I am available for deliveries, so that the system knows I am ready to accept jobs.

#### Acceptance Criteria

1. WHEN a driver sends a message containing "available", "online", or "ready", THE Driver_Message_Handler SHALL set the driver status to AVAILABLE
2. WHEN a driver status is changed to AVAILABLE, THE Driver_Message_Handler SHALL send a confirmation message to the driver
3. WHEN a driver with status AVAILABLE sends an availability message, THE Driver_Message_Handler SHALL send an already-available confirmation message
4. WHEN a driver with status PENDING_ACCEPTANCE sends an availability message, THE Driver_Message_Handler SHALL reject the request and inform the driver of their current state
5. WHEN a driver with status ON_DELIVERY sends an availability message, THE Driver_Message_Handler SHALL reject the request and inform the driver they must complete their delivery first

### Requirement 2: Mark Driver Offline

**User Story:** As a driver, I want to signal that I am going offline, so that the system stops offering me jobs.

#### Acceptance Criteria

1. WHEN a driver sends a message containing "offline", "break", or "offduty", THE Driver_Message_Handler SHALL set the driver status to OFFLINE
2. WHEN a driver status is changed to OFFLINE, THE Driver_Message_Handler SHALL send a confirmation message to the driver
3. WHEN a driver with status OFFLINE sends an offline message, THE Driver_Message_Handler SHALL send an already-offline confirmation message
4. WHEN a driver with status ON_DELIVERY sends an offline message, THE Driver_Message_Handler SHALL reject the request and inform the driver they must complete their delivery first
5. WHEN a driver with status PENDING_ACCEPTANCE sends an offline message, THE Driver_Message_Handler SHALL reject the request and inform the driver to respond to the pending job offer first

### Requirement 3: Track Messaging Window

**User Story:** As the system, I want to track when drivers last messaged, so that I am aware of the 24-hour messaging window status.

#### Acceptance Criteria

1. WHEN a driver sends any message, THE Driver_Message_Handler SHALL record the timestamp in Redis with key pattern "driver_window:{phone_number}"
2. THE Driver_Message_Handler SHALL set a 24-hour TTL on the driver_window key
3. WHEN checking messaging window status, THE Driver_Message_Handler SHALL use the presence of the driver_window key to determine if the window is open

### Requirement 4: Intent Parsing for Availability

**User Story:** As a developer, I want availability keywords parsed as distinct intents, so that the handler can process them appropriately.

#### Acceptance Criteria

1. WHEN the Intent_Parser receives a text message containing "available", "online", or "ready", THE Intent_Parser SHALL return ParsedIntent with intent "mark_available"
2. WHEN the Intent_Parser receives a text message containing "offline", "break", or "offduty", THE Intent_Parser SHALL return ParsedIntent with intent "mark_offline"
3. WHEN the Intent_Parser receives a text message containing availability keywords while in "pending_acceptance" state, THE Intent_Parser SHALL return ParsedIntent with intent "mark_available" or "mark_offline" (availability intents take precedence over state-specific parsing)
4. WHEN the Intent_Parser receives a text message containing availability keywords while in "on_delivery" state, THE Intent_Parser SHALL return ParsedIntent with intent "mark_available" or "mark_offline" (availability intents take precedence over state-specific parsing)

### Requirement 5: Response Messages

**User Story:** As a driver, I want clear confirmation messages when I change my availability, so that I know my status was updated.

#### Acceptance Criteria

1. WHEN a driver is marked AVAILABLE, THE Response_Builder SHALL return a message confirming availability and indicating readiness for job offers
2. WHEN a driver is marked OFFLINE, THE Response_Builder SHALL return a message confirming offline status
3. WHEN an availability change is rejected due to ON_DELIVERY status, THE Response_Builder SHALL return a message explaining the driver must complete their delivery first
4. WHEN an availability change is rejected due to PENDING_ACCEPTANCE status, THE Response_Builder SHALL return a message explaining the driver must respond to the pending job offer
5. WHEN a driver is already in the requested status, THE Response_Builder SHALL return a message indicating the current status

### Requirement 6: Help Message Update

**User Story:** As a driver, I want to know what commands are available, so that I can interact with the system effectively.

#### Acceptance Criteria

1. WHEN a driver sends "help" or "?", THE Driver_Message_Handler SHALL return a help message including availability commands
2. THE help message SHALL list "available", "online", "ready" as keywords to mark availability
3. THE help message SHALL list "offline", "break" as keywords to go offline