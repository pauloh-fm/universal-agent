from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from universal_agent.tools import clinic
from universal_agent.tools.scheduling import ClinicConfig, LocalCalendar, free_slots, load_clinic_config

from .conftest import ROOT, tool_call

CONFIG = load_clinic_config(ROOT / "agents" / "clinic-example" / "clinic.yaml")
# Monday 2026-11-09 07:00 in America/New_York (12:00 UTC).
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
MONDAY = date(2026, 11, 9)
TUESDAY = date(2026, 11, 10)


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    monkeypatch.setattr(clinic, "now", lambda: NOW)
    clinic._BACKENDS.clear()


def hhmm(slots):
    return [s.astimezone(CONFIG.tz).strftime("%H:%M") for s in slots]


def test_slots_respect_hours_lunch_and_notice() -> None:
    slots = hhmm(free_slots(CONFIG, CONFIG.service("general-consultation"), MONDAY, [], NOW))
    assert slots[0] == "09:00"  # 07:00 now + 2h notice
    assert "12:00" not in slots and "12:30" not in slots  # lunch break
    assert slots[-1] == "17:30"


def test_slots_skip_busy_and_long_services() -> None:
    busy_start = datetime(2026, 11, 10, 9, 0, tzinfo=CONFIG.tz)
    slots = hhmm(
        free_slots(CONFIG, CONFIG.service("physiotherapy"), TUESDAY, [(busy_start, busy_start + timedelta(minutes=30))], NOW)
    )
    assert "08:00" in slots  # ends 08:50, before the busy block
    assert "08:30" not in slots and "09:00" not in slots
    assert "09:30" in slots
    assert "11:30" not in slots  # 50 min would cross 12:00


def test_closed_days_and_window() -> None:
    service = CONFIG.service("follow-up")
    assert free_slots(CONFIG, service, date(2026, 11, 15), [], NOW) == []  # Sunday
    assert free_slots(CONFIG, service, date(2026, 12, 25), [], NOW) == []  # closed date
    assert free_slots(CONFIG, service, MONDAY + timedelta(days=90), [], NOW) == []  # beyond window


def test_config_validation() -> None:
    base = {"services": [{"id": "x", "name": "X", "duration_minutes": 30}]}
    with pytest.raises(ValueError):
        ClinicConfig.model_validate({**base, "opening_hours": {"monday": ["08:00-12:00"]}})
    with pytest.raises(ValueError):
        ClinicConfig.model_validate({**base, "opening_hours": {"mon": ["12:00-08:00"]}})
    with pytest.raises(ValueError):
        ClinicConfig.model_validate({**base, "timezone": "Mars/Base", "opening_hours": {}})


def test_local_calendar_prevents_double_booking(tmp_path: Path) -> None:
    from universal_agent.tools.scheduling import Appointment, SlotTakenError

    cal = LocalCalendar(tmp_path / "a.json")
    start = datetime(2026, 11, 10, 9, 0, tzinfo=CONFIG.tz)
    appt = Appointment("", "follow-up", "Follow-up", start, start + timedelta(minutes=20), "Pat", "5550100")
    assert cal.create(appt)
    with pytest.raises(SlotTakenError):
        cal.create(Appointment("", "follow-up", "Follow-up", start, start + timedelta(minutes=20), "Other", "5550199"))


BOOK = {
    "service_id": "general-consultation",
    "start": "2026-11-10 09:00",
    "patient_name": "Jane Doe",
    "patient_phone": "+1 555 0101",
}


async def test_booking_flow_requires_approval(make_runtime, settings) -> None:
    rt = make_runtime(
        [
            tool_call("find_available_slots", {"service_id": "general-consultation", "day": "2026-11-10"}),
            AIMessage(content="Tuesday 09:00 is free. Shall I book it?"),
            tool_call("book_appointment", BOOK, "call_2"),
            AIMessage(content="Your appointment is confirmed."),
        ]
    )
    first = await rt.chat("clinic-example", "p1", "I need a consultation tomorrow")
    assert first.reply == "Tuesday 09:00 is free. Shall I book it?"
    history = await rt.history("clinic-example", "p1")
    assert "09:00" in history[2]["content"]

    pending = await rt.chat("clinic-example", "p1", "yes, Jane Doe, +1 555 0101")
    assert pending.status == "awaiting_approval" and pending.pending_tool_calls[0]["name"] == "book_appointment"
    assert not (settings.data_dir / "clinic-example-appointments.json").exists()

    done = await rt.resume("clinic-example", "p1", approved=True)
    assert done.reply == "Your appointment is confirmed."
    tool_outputs = [m["content"] for m in await rt.history("clinic-example", "p1") if m["role"] == "tool"]
    assert tool_outputs[-1].startswith("Booked General consultation on 2026-11-10 09:00 for Jane Doe")

    # The slot is gone for the next patient.
    ctx_backend = clinic._BACKENDS[("clinic-example", str(settings.data_dir))]
    assert len(ctx_backend.find_by_phone("15550101", NOW)) == 1


async def test_booking_rejects_unavailable_time(make_runtime) -> None:
    bad = {**BOOK, "start": "2026-11-10 12:30"}  # lunch
    rt = make_runtime([tool_call("book_appointment", bad), AIMessage(content="That time is not available.")])
    await rt.chat("clinic-example", "p2", "book 12:30")
    await rt.resume("clinic-example", "p2", approved=True)
    outputs = [m["content"] for m in await rt.history("clinic-example", "p2") if m["role"] == "tool"]
    assert outputs[-1].startswith("error: that time is not available")


async def test_cancel_needs_matching_phone(make_runtime) -> None:
    rt = make_runtime(
        [
            tool_call("book_appointment", BOOK),
            AIMessage(content="Booked."),
            tool_call("find_my_appointments", {"patient_phone": "15550101"}, "c2"),
            AIMessage(content="Found it."),
        ]
    )
    await rt.chat("clinic-example", "p3", "book")
    await rt.resume("clinic-example", "p3", approved=True)
    await rt.chat("clinic-example", "p3", "my appointments?")
    listing = [m["content"] for m in await rt.history("clinic-example", "p3") if m["role"] == "tool"][-1]
    appointment_id = listing.split(":")[0].removeprefix("- ")

    rt2 = make_runtime(
        [
            tool_call("cancel_appointment", {"appointment_id": appointment_id, "patient_phone": "999999"}),
            AIMessage(content="Wrong phone."),
            tool_call("cancel_appointment", {"appointment_id": appointment_id, "patient_phone": "+1 (555) 0101"}, "c3"),
            AIMessage(content="Cancelled."),
        ]
    )
    await rt2.chat("clinic-example", "p4", "cancel")
    await rt2.resume("clinic-example", "p4", approved=True)
    await rt2.chat("clinic-example", "p4", "try my real phone")
    await rt2.resume("clinic-example", "p4", approved=True)
    outputs = [m["content"] for m in await rt2.history("clinic-example", "p4") if m["role"] == "tool"]
    assert outputs[0].startswith("error: no appointment")
    assert outputs[1].startswith("Cancelled General consultation")


async def test_clinic_info_shows_local_date(make_runtime) -> None:
    rt = make_runtime([tool_call("clinic_info", {}), AIMessage(content="ok")])
    await rt.chat("clinic-example", "p5", "hi")
    info = [m["content"] for m in await rt.history("clinic-example", "p5") if m["role"] == "tool"][0]
    assert "Now: 2026-11-09 07:00 (America/New_York, Monday)" in info
    assert "general-consultation: General consultation (30 min, price 120.00)" in info
