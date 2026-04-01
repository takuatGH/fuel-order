from dataclasses import dataclass, field

from .states import OrderState


@dataclass
class TextMessage:
    kind: str = "text"
    body: str = ""


@dataclass
class InteractiveButtonsMessage:
    kind: str = "buttons"
    body: str = ""
    buttons: list[dict[str, str]] = field(default_factory=list)
    header: str | None = None
    footer: str | None = None


@dataclass
class LocationRequestMessage:
    kind: str = "location_request"
    body: str = ""


OutboundMessage = TextMessage | InteractiveButtonsMessage | LocationRequestMessage

_FUEL_BUTTONS = [
    {"id": "fuel_diesel", "title": "Diesel"},
    {"id": "fuel_petrol", "title": "Petrol"},
    {"id": "fuel_paraffin", "title": "Paraffin"},
]

_CONFIRM_BUTTONS = [
    {"id": "confirm_yes", "title": "Confirm"},
    {"id": "confirm_no", "title": "Cancel"},
]


def fuel_type_prompt() -> InteractiveButtonsMessage:
    return InteractiveButtonsMessage(
        body="What type of fuel do you need?",
        buttons=_FUEL_BUTTONS,
    )


def quantity_prompt(fuel_type: str) -> TextMessage:
    return TextMessage(
        body=f"Got it, *{fuel_type.title()}*.\n\nHow many liters do you need?\n(Min: 10L, Max: 10,000L)"
    )


def location_prompt(quantity: float, fuel_type: str) -> LocationRequestMessage:
    return LocationRequestMessage(
        body=f"*{quantity:.0f} liters* of {fuel_type}.\n\nTap below to share your delivery location."
    )


def confirmation_prompt(fuel_type: str, quantity: float, address: str) -> InteractiveButtonsMessage:
    return InteractiveButtonsMessage(
        body=(
            "*Order Summary*\n\n"
            f"• Fuel: {fuel_type.title()}\n"
            f"• Quantity: {quantity:.0f} liters\n"
            f"• Location: {address}"
        ),
        buttons=_CONFIRM_BUTTONS,
    )


def order_placed_message() -> TextMessage:
    return TextMessage(
        body=(
            "✅ *Order Placed!*\n\n"
            "We're finding the nearest depot to fulfill your order. "
            "You'll receive updates on delivery status."
        )
    )


def cancelled_message() -> TextMessage:
    return TextMessage(body="Order cancelled.\n\nSend *order* anytime to start a new order.")


def help_message() -> TextMessage:
    return TextMessage(
        body=(
            "*FuelFlow Help*\n\n"
            "Send *order* to place a fuel order.\n"
            "Send *cancel* anytime to cancel.\n\n"
            "*Order steps:*\n"
            "1. Choose fuel type\n"
            "2. Enter quantity (10–10,000 L)\n"
            "3. Share location\n"
            "4. Confirm"
        )
    )


def greeting_message() -> TextMessage:
    return TextMessage(
        body="👋 Hi! I'm FuelFlow, your fuel delivery assistant.\n\nSend *order* to place a fuel order, or *help* for options."
    )


def invalid_fuel_type_error() -> InteractiveButtonsMessage:
    return InteractiveButtonsMessage(
        body="Sorry, please choose a fuel type:",
        buttons=_FUEL_BUTTONS,
    )


def invalid_quantity_error() -> TextMessage:
    return TextMessage(
        body="Please enter a number between 10 and 10,000 liters.\n\nExample: *200* or *500L*"
    )


def invalid_confirmation_error() -> InteractiveButtonsMessage:
    return InteractiveButtonsMessage(
        body="Please tap Confirm or Cancel:",
        buttons=_CONFIRM_BUTTONS,
    )


def reprompt(state: str) -> OutboundMessage:
    if state == OrderState.AWAITING_FUEL_TYPE.value:
        return InteractiveButtonsMessage(
            body="What type of fuel do you need?",
            buttons=_FUEL_BUTTONS,
        )
    if state == OrderState.AWAITING_QUANTITY.value:
        return TextMessage(body="How many liters do you need?\n(Between 10 and 10,000 liters)")
    if state == OrderState.AWAITING_LOCATION.value:
        return LocationRequestMessage(body="Where should we deliver?\n\nTap below to share your location.")
    if state == OrderState.AWAITING_CONFIRMATION.value:
        return InteractiveButtonsMessage(
            body="Tap Confirm to place your order, or Cancel to start over:",
            buttons=_CONFIRM_BUTTONS,
        )
    return TextMessage(body="Send *order* to place a fuel order, or *help* for options.")
