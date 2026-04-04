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

_JOB_OFFER_BUTTONS = [
    {"id": "job_accept", "title": "Accept Job"},
    {"id": "job_decline", "title": "Decline"},
]

_DELIVERY_OVERRIDE_BUTTONS = [
    {"id": "delivery_override_yes", "title": "Yes, delivered"},
    {"id": "delivery_override_no", "title": "Not yet"},
]


def welcome_message() -> TextMessage:
    return TextMessage(
        body="Welcome to *FuelFlow*! We'll get your fuel delivery sorted."
    )


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
        body="Hi! I'm FuelFlow, your fuel delivery assistant.\n\nSend any message to get started, or *help* for options."
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


def driver_job_offer(order_number: str, fuel_type: str, quantity: float, address: str) -> InteractiveButtonsMessage:
    return InteractiveButtonsMessage(
        body=(
            f"*New Job: {order_number}*\n\n"
            f"• Fuel: {fuel_type.title()}\n"
            f"• Quantity: {quantity:.0f}L\n"
            f"• Deliver to: {address}"
        ),
        buttons=_JOB_OFFER_BUTTONS,
        footer="Offer expires in 5 minutes",
    )


def driver_job_confirmed(address: str) -> TextMessage:
    return TextMessage(
        body=f"Job confirmed! Head to:\n{address}\n\nShare your location or type *delivered* when done."
    )


def driver_job_declined() -> TextMessage:
    return TextMessage(body="Noted. Thanks for letting us know.")


def driver_offer_expired() -> TextMessage:
    return TextMessage(body="This job offer has expired.")


def driver_no_active_offer() -> TextMessage:
    return TextMessage(body="No active job at the moment.")


def driver_delivery_prompt() -> TextMessage:
    return TextMessage(body="Share your location or type *delivered* to complete the job.")


def driver_delivery_confirmed(order_number: str) -> TextMessage:
    return TextMessage(body=f"Delivery confirmed for {order_number}. Great work!")


def driver_delivery_location_warning(distance_m: float, order_number: str) -> InteractiveButtonsMessage:
    dist_km = distance_m / 1000
    return InteractiveButtonsMessage(
        body=(
            f"You appear to be *{dist_km:.1f}km* from the delivery point for {order_number}.\n\n"
            "Has the delivery been completed?"
        ),
        buttons=_DELIVERY_OVERRIDE_BUTTONS,
    )


def shop_driver_assigned(driver_name: str, vehicle_plate: str) -> TextMessage:
    return TextMessage(
        body=f"Driver *{driver_name}* ({vehicle_plate}) has accepted your order and is on the way."
    )


def shop_no_drivers_available(order_number: str) -> TextMessage:
    return TextMessage(
        body=f"Sorry, no drivers are available for order {order_number} right now. We'll retry shortly."
    )


def shop_order_delivered(order_number: str) -> TextMessage:
    return TextMessage(body=f"Your order *{order_number}* has been delivered.")


def admin_order_completed(
    order_number: str,
    fuel_type: str,
    quantity: float,
    shop_phone: str,
    driver_name: str,
    vehicle_plate: str,
    address: str,
) -> TextMessage:
    return TextMessage(body=(
        f"Order Completed\n"
        f"Order: {order_number}\n"
        f"Fuel: {quantity:.0f}L {fuel_type}\n"
        f"Shop: {shop_phone}\n"
        f"Driver: {driver_name} ({vehicle_plate})\n"
        f"Address: {address}"
    ))


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
