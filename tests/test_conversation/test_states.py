import pytest
from src.conversation.responses import (
    InteractiveButtonsMessage, LocationRequestMessage, OutboundMessage, TextMessage,
)
from src.conversation.states import OrderDraft, OrderFlow, OrderState


# --- helpers ---

def make_flow(state: str | None = None) -> tuple[OrderFlow, list[OutboundMessage]]:
    msgs: list[OutboundMessage] = []
    f = OrderFlow("test")
    if state:
        f.state = state
    f.message_callback = msgs.append
    return f, msgs


# --- OrderDraft ---

def test_draft_is_complete_when_all_fields_set():
    d = OrderDraft(fuel_type="diesel", quantity_liters=100.0, latitude=-26.2, longitude=28.0)
    assert d.is_complete()


def test_draft_is_incomplete_when_field_missing():
    d = OrderDraft(fuel_type="diesel", quantity_liters=100.0, latitude=-26.2)
    assert not d.is_complete()


def test_draft_round_trips_through_dict():
    d = OrderDraft(fuel_type="petrol", quantity_liters=500.0, latitude=-33.9, longitude=18.4)
    assert OrderDraft.from_dict(d.to_dict()) == d


def test_draft_from_empty_dict_gives_none_fields():
    d = OrderDraft.from_dict({})
    assert d.fuel_type is None
    assert d.quantity_liters is None


# --- happy path ---

def test_full_order_flow():
    f, msgs = make_flow()

    assert f.process_input(None, "start_order")
    assert f.state == OrderState.AWAITING_FUEL_TYPE.value

    assert f.process_input("diesel", "fuel_selected")
    assert f.state == OrderState.AWAITING_QUANTITY.value
    assert f.draft.fuel_type == "diesel"

    assert f.process_input("200", "quantity_provided")
    assert f.state == OrderState.AWAITING_LOCATION.value
    assert f.draft.quantity_liters == 200.0

    assert f.process_input({"latitude": -26.2041, "longitude": 28.0473}, "location_provided")
    assert f.state == OrderState.AWAITING_CONFIRMATION.value
    assert f.draft.latitude == -26.2041
    assert f.draft.longitude == 28.0473

    assert f.process_input(None, "confirm_order")
    assert f.state == OrderState.ORDER_PLACED.value

    assert len(msgs) == 5  # welcome + fuel prompt + quantity + location + confirmation (order placed sent by webhook)


def test_on_order_placed_appends_pending_event():
    f, _ = make_flow()
    f.process_input(None, "start_order")
    f.process_input("diesel", "fuel_selected")
    f.process_input("100", "quantity_provided")
    f.process_input({"latitude": -26.2, "longitude": 28.0}, "location_provided")
    f.process_input(None, "confirm_order")

    assert len(f.pending_events) == 1
    event = f.pending_events[0]
    assert event["type"] == "order_created"
    assert event["draft"]["fuel_type"] == "diesel"


def test_reset_returns_to_idle_and_clears_draft():
    f, _ = make_flow(OrderState.ORDER_PLACED.value)
    f.draft.fuel_type = "petrol"
    f.reset()
    assert f.state == OrderState.IDLE.value
    assert f.draft.fuel_type is None


# --- cancel ---

@pytest.mark.parametrize("state", [
    OrderState.AWAITING_FUEL_TYPE.value,
    OrderState.AWAITING_QUANTITY.value,
    OrderState.AWAITING_LOCATION.value,
    OrderState.AWAITING_CONFIRMATION.value,
])
def test_cancel_from_any_active_state(state):
    f, msgs = make_flow(state)
    f.draft.fuel_type = "diesel"
    assert f.process_input(None, "cancel")
    assert f.state == OrderState.IDLE.value
    assert f.draft.fuel_type is None
    assert any("cancel" in m.body.lower() for m in msgs)


def test_cancel_from_idle_is_ignored():
    f, _ = make_flow()
    assert not f.process_input(None, "cancel")
    assert f.state == OrderState.IDLE.value


def test_cancel_from_order_placed_is_ignored():
    f, _ = make_flow(OrderState.ORDER_PLACED.value)
    assert not f.process_input(None, "cancel")
    assert f.state == OrderState.ORDER_PLACED.value


# --- validation guards ---

@pytest.mark.parametrize("value", ["diesel", "petrol", "paraffin", "DIESEL", "Petrol"])
def test_valid_fuel_types_accepted(value):
    f, _ = make_flow(OrderState.AWAITING_FUEL_TYPE.value)
    assert f.process_input(value, "fuel_selected")
    assert f.state == OrderState.AWAITING_QUANTITY.value


@pytest.mark.parametrize("value", ["unleaded", "gas", "coal", "", "123"])
def test_invalid_fuel_types_rejected(value):
    f, _ = make_flow(OrderState.AWAITING_FUEL_TYPE.value)
    assert not f.process_input(value, "fuel_selected")
    assert f.state == OrderState.AWAITING_FUEL_TYPE.value


@pytest.mark.parametrize("value", ["10", "100", "10000", "500.5"])
def test_valid_quantities_accepted(value):
    f, _ = make_flow(OrderState.AWAITING_QUANTITY.value)
    f.draft.fuel_type = "diesel"
    assert f.process_input(value, "quantity_provided")
    assert f.state == OrderState.AWAITING_LOCATION.value


@pytest.mark.parametrize("value", ["9", "10001", "0", "-50", "abc", ""])
def test_invalid_quantities_rejected(value):
    f, _ = make_flow(OrderState.AWAITING_QUANTITY.value)
    f.draft.fuel_type = "diesel"
    assert not f.process_input(value, "quantity_provided")
    assert f.state == OrderState.AWAITING_QUANTITY.value


def test_location_dict_saves_coordinates():
    f, _ = make_flow(OrderState.AWAITING_LOCATION.value)
    f.draft.fuel_type = "diesel"
    f.draft.quantity_liters = 100.0
    f.process_input({"latitude": -33.9, "longitude": 18.4}, "location_provided")
    assert f.draft.latitude == -33.9
    assert f.draft.longitude == 18.4


def test_location_text_rejected():
    # Text addresses are no longer accepted — GPS share is required
    f, _ = make_flow(OrderState.AWAITING_LOCATION.value)
    f.draft.fuel_type = "diesel"
    f.draft.quantity_liters = 100.0
    result = f.process_input("123 Main St", "location_provided")
    assert result is False
    assert f.state == OrderState.AWAITING_LOCATION.value
    assert f.draft.latitude is None
    assert f.draft.longitude is None


def test_empty_location_rejected():
    f, _ = make_flow(OrderState.AWAITING_LOCATION.value)
    assert not f.process_input("", "location_provided")
    assert f.state == OrderState.AWAITING_LOCATION.value


# --- wrong-state transitions ---

def test_fuel_selected_ignored_when_not_awaiting_fuel():
    f, _ = make_flow(OrderState.AWAITING_QUANTITY.value)
    assert not f.process_input("diesel", "fuel_selected")
    assert f.state == OrderState.AWAITING_QUANTITY.value


def test_confirm_ignored_when_not_awaiting_confirmation():
    f, _ = make_flow(OrderState.AWAITING_FUEL_TYPE.value)
    assert not f.process_input(None, "confirm_order")
    assert f.state == OrderState.AWAITING_FUEL_TYPE.value


def test_unknown_intent_returns_false():
    f, _ = make_flow()
    assert not f.process_input("anything", "nonexistent_trigger")
    assert f.state == OrderState.IDLE.value


# --- redis serialisation ---

def test_session_round_trip_preserves_state_and_draft():
    f, _ = make_flow()
    f.state = OrderState.AWAITING_QUANTITY.value
    f.draft.fuel_type = "paraffin"
    f.draft.quantity_liters = 300.0

    restored = OrderFlow.from_session_data("test", f.to_session_data())
    assert restored.state == f.state
    assert restored.draft.fuel_type == "paraffin"
    assert restored.draft.quantity_liters == 300.0


def test_session_defaults_to_idle_on_missing_data():
    f = OrderFlow.from_session_data("test", {})
    assert f.state == OrderState.IDLE.value
    assert f.draft.fuel_type is None


# --- message callbacks ---

def test_no_message_sent_when_callback_not_set():
    f = OrderFlow("test")
    f.process_input(None, "start_order")
    assert f.state == OrderState.AWAITING_FUEL_TYPE.value


def test_message_sent_on_every_state_transition():
    f, msgs = make_flow()
    f.process_input(None, "start_order")
    assert len(msgs) == 2  # welcome TextMessage + fuel type InteractiveButtonsMessage
    assert isinstance(msgs[0], TextMessage)
    assert isinstance(msgs[1], InteractiveButtonsMessage)
    f.process_input("diesel", "fuel_selected")
    assert len(msgs) == 3
    assert isinstance(msgs[2], TextMessage)


def test_no_message_on_failed_transition():
    f, msgs = make_flow(OrderState.AWAITING_FUEL_TYPE.value)
    f.process_input("invalid_fuel", "fuel_selected")
    assert len(msgs) == 0
