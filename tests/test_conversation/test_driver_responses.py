import pytest
from src.conversation.responses import (
    InteractiveButtonsMessage,
    TextMessage,
    admin_order_completed,
    driver_delivery_confirmed,
    driver_delivery_location_warning,
    driver_delivery_prompt,
    driver_job_confirmed,
    driver_job_declined,
    driver_job_offer,
    driver_no_active_offer,
    driver_offer_expired,
    shop_driver_assigned,
    shop_no_drivers_available,
    shop_order_delivered,
)


# --- type checks ---

def test_driver_job_offer_is_buttons():
    msg = driver_job_offer("FO-20260401-001", "diesel", 200.0, "123 Main St")
    assert isinstance(msg, InteractiveButtonsMessage)


def test_driver_job_confirmed_is_text():
    assert isinstance(driver_job_confirmed("123 Main St"), TextMessage)


def test_driver_job_declined_is_text():
    assert isinstance(driver_job_declined(), TextMessage)


def test_driver_offer_expired_is_text():
    assert isinstance(driver_offer_expired(), TextMessage)


def test_driver_no_active_offer_is_text():
    assert isinstance(driver_no_active_offer(), TextMessage)


def test_driver_delivery_prompt_is_text():
    assert isinstance(driver_delivery_prompt(), TextMessage)


def test_driver_delivery_confirmed_is_text():
    assert isinstance(driver_delivery_confirmed("FO-20260401-001"), TextMessage)


def test_driver_delivery_location_warning_is_buttons():
    msg = driver_delivery_location_warning(1500.0, "FO-20260401-001")
    assert isinstance(msg, InteractiveButtonsMessage)


def test_shop_driver_assigned_is_text():
    assert isinstance(shop_driver_assigned("Sipho Nkosi", "GP 12 AB"), TextMessage)


def test_shop_no_drivers_available_is_text():
    assert isinstance(shop_no_drivers_available("FO-20260401-001"), TextMessage)


def test_shop_order_delivered_is_text():
    assert isinstance(shop_order_delivered("FO-20260401-001"), TextMessage)


def test_admin_order_completed_is_text():
    msg = admin_order_completed("FO-001", "diesel", 200.0, "27821234567", "Sipho", "GP 12 AB", "Main St")
    assert isinstance(msg, TextMessage)


# --- button ID correctness ---

def test_driver_job_offer_button_ids():
    msg = driver_job_offer("FO-001", "diesel", 200.0, "addr")
    ids = {b["id"] for b in msg.buttons}
    assert ids == {"job_accept", "job_decline"}


def test_delivery_location_warning_button_ids():
    msg = driver_delivery_location_warning(600.0, "FO-001")
    ids = {b["id"] for b in msg.buttons}
    assert ids == {"delivery_override_yes", "delivery_override_no"}


# --- WhatsApp constraints ---

@pytest.mark.parametrize("msg", [
    driver_job_offer("FO-001", "diesel", 200.0, "addr"),
    driver_delivery_location_warning(1500.0, "FO-001"),
])
def test_button_titles_within_20_chars(msg):
    for btn in msg.buttons:
        assert len(btn["title"]) <= 20, f"title too long: {btn['title']!r}"


@pytest.mark.parametrize("msg", [
    driver_job_offer("FO-001", "diesel", 200.0, "addr"),
    driver_delivery_location_warning(1500.0, "FO-001"),
])
def test_max_3_buttons(msg):
    assert len(msg.buttons) <= 3


@pytest.mark.parametrize("fn,args", [
    (driver_job_offer, ("FO-001", "diesel", 200.0, "123 Main St, Johannesburg")),
    (driver_job_confirmed, ("123 Main St",)),
    (driver_job_declined, ()),
    (driver_offer_expired, ()),
    (driver_no_active_offer, ()),
    (driver_delivery_prompt, ()),
    (driver_delivery_confirmed, ("FO-001",)),
    (driver_delivery_location_warning, (600.0, "FO-001")),
    (shop_driver_assigned, ("Sipho Nkosi", "GP 12 AB")),
    (shop_no_drivers_available, ("FO-001",)),
    (shop_order_delivered, ("FO-001",)),
])
def test_body_within_1024_chars(fn, args):
    assert len(fn(*args).body) <= 1024


# --- content sanity ---

def test_driver_job_offer_includes_order_number():
    msg = driver_job_offer("FO-20260401-007", "petrol", 150.0, "addr")
    assert "FO-20260401-007" in msg.body


def test_driver_job_offer_includes_quantity_and_fuel():
    msg = driver_job_offer("FO-001", "diesel", 300.0, "addr")
    assert "300" in msg.body
    assert "Diesel" in msg.body


def test_driver_job_offer_has_expiry_footer():
    msg = driver_job_offer("FO-001", "diesel", 200.0, "addr")
    assert msg.footer is not None
    assert len(msg.footer) > 0


def test_driver_delivery_confirmed_includes_order_number():
    msg = driver_delivery_confirmed("FO-20260401-003")
    assert "FO-20260401-003" in msg.body


def test_driver_delivery_location_warning_includes_distance():
    msg = driver_delivery_location_warning(2500.0, "FO-001")
    assert "2.5" in msg.body


def test_shop_driver_assigned_includes_name_and_plate():
    msg = shop_driver_assigned("Lerato Mokoena", "NW 78 GH")
    assert "Lerato Mokoena" in msg.body
    assert "NW 78 GH" in msg.body


def test_admin_order_completed_includes_all_fields():
    msg = admin_order_completed("FO-001", "diesel", 200.0, "27821234567", "Sipho", "GP 12 AB", "Main St")
    assert "FO-001" in msg.body
    assert "diesel" in msg.body
    assert "200" in msg.body
    assert "27821234567" in msg.body
    assert "Sipho" in msg.body
    assert "GP 12 AB" in msg.body
    assert "Main St" in msg.body
