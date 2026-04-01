import pytest
from src.conversation.responses import (
    InteractiveButtonsMessage,
    LocationRequestMessage,
    OutboundMessage,
    TextMessage,
    cancelled_message,
    confirmation_prompt,
    fuel_type_prompt,
    greeting_message,
    help_message,
    invalid_confirmation_error,
    invalid_fuel_type_error,
    invalid_quantity_error,
    location_prompt,
    order_placed_message,
    quantity_prompt,
    reprompt,
)
from src.conversation.states import OrderState


# --- type checks ---

def test_fuel_type_prompt_is_buttons():
    msg = fuel_type_prompt()
    assert isinstance(msg, InteractiveButtonsMessage)
    assert len(msg.buttons) == 3


def test_quantity_prompt_is_text():
    assert isinstance(quantity_prompt("diesel"), TextMessage)


def test_location_prompt_is_location_request():
    assert isinstance(location_prompt(200.0, "diesel"), LocationRequestMessage)


def test_confirmation_prompt_is_buttons():
    msg = confirmation_prompt("diesel", 200.0, "-26.2041, 28.0473")
    assert isinstance(msg, InteractiveButtonsMessage)
    assert len(msg.buttons) == 2


def test_order_placed_message_is_text():
    assert isinstance(order_placed_message(), TextMessage)


def test_cancelled_message_is_text():
    assert isinstance(cancelled_message(), TextMessage)


def test_help_message_is_text():
    assert isinstance(help_message(), TextMessage)


def test_greeting_message_is_text():
    assert isinstance(greeting_message(), TextMessage)


def test_invalid_fuel_type_error_is_buttons():
    msg = invalid_fuel_type_error()
    assert isinstance(msg, InteractiveButtonsMessage)
    assert len(msg.buttons) == 3


def test_invalid_quantity_error_is_text():
    assert isinstance(invalid_quantity_error(), TextMessage)


def test_invalid_confirmation_error_is_buttons():
    msg = invalid_confirmation_error()
    assert isinstance(msg, InteractiveButtonsMessage)
    assert len(msg.buttons) == 2


# --- button id correctness (must match intents.py _parse_button_id) ---

def test_fuel_buttons_have_correct_ids():
    buttons = fuel_type_prompt().buttons
    ids = {b["id"] for b in buttons}
    assert ids == {"fuel_diesel", "fuel_petrol", "fuel_paraffin"}


def test_confirm_buttons_have_correct_ids():
    buttons = confirmation_prompt("diesel", 100.0, "addr").buttons
    ids = {b["id"] for b in buttons}
    assert ids == {"confirm_yes", "confirm_no"}


def test_invalid_fuel_buttons_match_fuel_type_prompt():
    assert invalid_fuel_type_error().buttons == fuel_type_prompt().buttons


def test_invalid_confirm_buttons_match_confirmation_prompt():
    assert invalid_confirmation_error().buttons == confirmation_prompt("d", 10, "a").buttons


# --- whatsapp constraints ---

@pytest.mark.parametrize("msg", [
    fuel_type_prompt(),
    confirmation_prompt("diesel", 200.0, "addr"),
    invalid_fuel_type_error(),
    invalid_confirmation_error(),
])
def test_button_titles_within_20_chars(msg):
    for btn in msg.buttons:
        assert len(btn["title"]) <= 20, f"title too long: {btn['title']!r}"


@pytest.mark.parametrize("msg", [
    fuel_type_prompt(),
    confirmation_prompt("diesel", 200.0, "addr"),
    invalid_fuel_type_error(),
    invalid_confirmation_error(),
])
def test_max_3_buttons(msg):
    assert len(msg.buttons) <= 3


@pytest.mark.parametrize("fn,args", [
    (fuel_type_prompt, ()),
    (quantity_prompt, ("diesel",)),
    (location_prompt, (200.0, "diesel")),
    (order_placed_message, ()),
    (cancelled_message, ()),
    (help_message, ()),
    (greeting_message, ()),
    (invalid_fuel_type_error, ()),
    (invalid_quantity_error, ()),
    (invalid_confirmation_error, ()),
])
def test_body_within_1024_chars(fn, args):
    msg = fn(*args)
    assert len(msg.body) <= 1024


# --- content sanity ---

def test_quantity_prompt_includes_fuel_type():
    msg = quantity_prompt("petrol")
    assert "Petrol" in msg.body


def test_location_prompt_includes_quantity():
    msg = location_prompt(500.0, "diesel")
    assert "500" in msg.body


def test_confirmation_prompt_includes_all_fields():
    msg = confirmation_prompt("diesel", 200.0, "-26.2041, 28.0473")
    assert "Diesel" in msg.body
    assert "200" in msg.body
    assert "-26.2041" in msg.body


# --- reprompt returns correct type per state ---

@pytest.mark.parametrize("state,expected_type", [
    (OrderState.AWAITING_FUEL_TYPE.value, InteractiveButtonsMessage),
    (OrderState.AWAITING_QUANTITY.value, TextMessage),
    (OrderState.AWAITING_LOCATION.value, LocationRequestMessage),
    (OrderState.AWAITING_CONFIRMATION.value, InteractiveButtonsMessage),
    (OrderState.IDLE.value, TextMessage),
])
def test_reprompt_returns_correct_type(state, expected_type):
    assert isinstance(reprompt(state), expected_type)
