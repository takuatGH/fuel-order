import pytest
from src.conversation.intents import IntentParser, ParsedIntent
from src.conversation.states import OrderState


@pytest.fixture
def parser():
    return IntentParser()


def btn(button_id: str) -> dict:
    return {"type": "interactive", "interactive": {"button_reply": {"id": button_id}}}


def txt(body: str) -> dict:
    return {"type": "text", "text": {"body": body}}


def loc(lat: float, lng: float) -> dict:
    return {"type": "location", "location": {"latitude": lat, "longitude": lng}}


# --- driver job offer buttons ---

def test_job_accept_button(parser):
    r = parser.parse(btn("job_accept"), current_state="pending_acceptance")
    assert r.intent == "accept_job"


def test_job_decline_button(parser):
    r = parser.parse(btn("job_decline"), current_state="pending_acceptance")
    assert r.intent == "decline_job"


def test_job_accept_is_context_independent(parser):
    for state in [OrderState.IDLE.value, "on_delivery", "pending_acceptance"]:
        r = parser.parse(btn("job_accept"), current_state=state)
        assert r.intent == "accept_job"


def test_job_decline_is_context_independent(parser):
    for state in [OrderState.IDLE.value, "on_delivery", "pending_acceptance"]:
        r = parser.parse(btn("job_decline"), current_state=state)
        assert r.intent == "decline_job"


# --- delivery override buttons ---

def test_delivery_override_yes_maps_to_delivery_confirmed(parser):
    r = parser.parse(btn("delivery_override_yes"), current_state="on_delivery")
    assert r.intent == "delivery_confirmed"


def test_delivery_override_no_maps_to_delivery_override_cancel(parser):
    r = parser.parse(btn("delivery_override_no"), current_state="on_delivery")
    assert r.intent == "delivery_override_cancel"


# --- delivery confirmation text ---

@pytest.mark.parametrize("text", ["delivered", "done", "complete", "delivery done", "delivery complete"])
def test_delivery_text_triggers_in_on_delivery_state(parser, text):
    r = parser.parse(txt(text), current_state="on_delivery")
    assert r.intent == "delivery_confirmed"


@pytest.mark.parametrize("text", ["DELIVERED", "Done", "COMPLETE"])
def test_delivery_text_is_case_insensitive(parser, text):
    r = parser.parse(txt(text), current_state="on_delivery")
    assert r.intent == "delivery_confirmed"


def test_unrecognised_text_in_on_delivery_state_returns_unknown(parser):
    r = parser.parse(txt("hello there"), current_state="on_delivery")
    assert r.intent == "unknown"


# --- location on_delivery state ---

def test_location_in_on_delivery_state_returns_location_provided(parser):
    r = parser.parse(loc(-26.2041, 28.0473), current_state="on_delivery")
    assert r.intent == "location_provided"
    assert r.value == {"latitude": -26.2041, "longitude": 28.0473}


def test_location_in_awaiting_location_state_still_works(parser):
    r = parser.parse(loc(-26.2041, 28.0473), current_state=OrderState.AWAITING_LOCATION.value)
    assert r.intent == "location_provided"


# --- any message in idle starts an order ---

@pytest.mark.parametrize("text", ["hi", "hello", "I need fuel", "order", "diesel", "random text", "1"])
def test_any_text_in_idle_triggers_start_order(parser, text):
    r = parser.parse(txt(text), current_state=OrderState.IDLE.value)
    assert r.intent == "start_order"


def test_any_text_in_order_placed_triggers_start_order(parser):
    r = parser.parse(txt("hi again"), current_state=OrderState.ORDER_PLACED.value)
    assert r.intent == "start_order"


# --- existing button IDs not broken ---

def test_fuel_buttons_still_work(parser):
    for bid, fuel in [("fuel_diesel", "diesel"), ("fuel_petrol", "petrol"), ("fuel_paraffin", "paraffin")]:
        r = parser.parse(btn(bid), current_state=OrderState.AWAITING_FUEL_TYPE.value)
        assert r.intent == "fuel_selected"
        assert r.value == fuel


def test_confirm_yes_still_works(parser):
    r = parser.parse(btn("confirm_yes"), current_state=OrderState.AWAITING_CONFIRMATION.value)
    assert r.intent == "confirm_order"


def test_confirm_no_still_works(parser):
    r = parser.parse(btn("confirm_no"), current_state=OrderState.AWAITING_CONFIRMATION.value)
    assert r.intent == "cancel"


# --- availability intents ---

@pytest.mark.parametrize("keyword", ["available", "online", "ready"])
def test_availability_keywords_trigger_mark_available(parser, keyword):
    r = parser.parse(txt(keyword), current_state="idle")
    assert r.intent == "mark_available"


@pytest.mark.parametrize("keyword", ["offline", "break", "offduty"])
def test_offline_keywords_trigger_mark_offline(parser, keyword):
    r = parser.parse(txt(keyword), current_state="idle")
    assert r.intent == "mark_offline"


@pytest.mark.parametrize("keyword", ["AVAILABLE", "Online", "READY"])
def test_availability_keywords_are_case_insensitive(parser, keyword):
    r = parser.parse(txt(keyword), current_state="idle")
    assert r.intent == "mark_available"


@pytest.mark.parametrize("keyword", ["OFFLINE", "Break", "OFFDUTY"])
def test_offline_keywords_are_case_insensitive(parser, keyword):
    r = parser.parse(txt(keyword), current_state="idle")
    assert r.intent == "mark_offline"


@pytest.mark.parametrize("text", ["I'm available now", "going online", "ready for jobs"])
def test_availability_keywords_work_as_substrings(parser, text):
    r = parser.parse(txt(text), current_state="pending_acceptance")
    assert r.intent == "mark_available"


@pytest.mark.parametrize("text", ["going offline now", "taking a break", "i am offduty"])
def test_offline_keywords_work_as_substrings(parser, text):
    r = parser.parse(txt(text), current_state="pending_acceptance")
    assert r.intent == "mark_offline"


@pytest.mark.parametrize("state", [
    OrderState.IDLE.value,
    OrderState.AWAITING_FUEL_TYPE.value,
    OrderState.AWAITING_QUANTITY.value,
    OrderState.AWAITING_CONFIRMATION.value,
    "pending_acceptance",
    "on_delivery",
])
def test_availability_intents_work_in_all_states(parser, state):
    assert parser.parse(txt("available"), current_state=state).intent == "mark_available"
    assert parser.parse(txt("offline"), current_state=state).intent == "mark_offline"
