"""GoogleCalendar backend against an in-memory fake of the Calendar API client (no network)."""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from universal_agent.tools.google_calendar import GoogleCalendar
from universal_agent.tools.scheduling import Appointment, SlotTakenError

TZ = ZoneInfo("America/New_York")


class _Req:
    def __init__(self, fn: Any) -> None:
        self.fn = fn

    def execute(self) -> Any:
        return self.fn()


class FakeCalendarApi:
    """Implements the subset of googleapiclient's Calendar v3 resource used by GoogleCalendar."""

    def __init__(self) -> None:
        self.events_by_id: dict[str, dict[str, Any]] = {}
        self.calls: list[str] = []

    def freebusy(self) -> "FakeCalendarApi":
        return self

    def events(self) -> "FakeCalendarApi":
        return self

    def query(self, body: dict[str, Any]) -> _Req:
        self.calls.append("freebusy")
        t0, t1 = datetime.fromisoformat(body["timeMin"]), datetime.fromisoformat(body["timeMax"])
        busy = [
            {"start": e["start"]["dateTime"], "end": e["end"]["dateTime"]}
            for e in self.events_by_id.values()
            if datetime.fromisoformat(e["start"]["dateTime"]) < t1 and t0 < datetime.fromisoformat(e["end"]["dateTime"])
        ]
        cal_id = body["items"][0]["id"]
        return _Req(lambda: {"calendars": {cal_id: {"busy": busy}}})

    def insert(self, calendarId: str, body: dict[str, Any]) -> _Req:  # noqa: N803 - mirrors Google API
        self.calls.append("insert")
        event_id = f"evt{len(self.events_by_id) + 1}"
        self.events_by_id[event_id] = {**body, "id": event_id, "status": "confirmed"}
        return _Req(lambda: self.events_by_id[event_id])

    def get(self, calendarId: str, eventId: str) -> _Req:  # noqa: N803
        return _Req(lambda: self.events_by_id[eventId])

    def delete(self, calendarId: str, eventId: str, sendUpdates: str) -> _Req:  # noqa: N803
        self.calls.append("delete")
        return _Req(lambda: self.events_by_id.pop(eventId))

    def list(self, calendarId: str, privateExtendedProperty: list[str], **_: Any) -> _Req:  # noqa: N803
        wanted = dict(p.split("=", 1) for p in privateExtendedProperty)
        items = [e for e in self.events_by_id.values() if wanted.items() <= e["extendedProperties"]["private"].items()]
        return _Req(lambda: {"items": items})


def make_appointment(hour: int = 9) -> Appointment:
    start = datetime(2026, 11, 10, hour, 0, tzinfo=TZ)
    return Appointment(
        "", "follow-up", "Follow-up visit", start, start + timedelta(minutes=20), "Jane Doe", "15550101", "first visit"
    )


def test_create_get_find_cancel() -> None:
    api = FakeCalendarApi()
    cal = GoogleCalendar(api, "clinic@group.calendar.google.com", "America/New_York")
    event_id = cal.create(make_appointment())
    event = api.events_by_id[event_id]
    assert event["summary"] == "Follow-up visit - Jane Doe"
    assert event["start"] == {"dateTime": "2026-11-10T09:00:00-05:00", "timeZone": "America/New_York"}
    assert event["extendedProperties"]["private"]["patient_phone"] == "15550101"

    got = cal.get(event_id)
    assert got is not None and got.patient_name == "Jane Doe" and got.start == make_appointment().start
    assert [a.id for a in cal.find_by_phone("15550101", datetime(2026, 11, 1, tzinfo=TZ))] == [event_id]
    assert cal.busy(datetime(2026, 11, 10, tzinfo=TZ), datetime(2026, 11, 11, tzinfo=TZ))

    cal.cancel(event_id)
    assert api.calls[-1] == "delete" and not api.events_by_id


def test_create_rechecks_free_busy() -> None:
    cal = GoogleCalendar(FakeCalendarApi(), "cal", "America/New_York")
    cal.create(make_appointment())
    with pytest.raises(SlotTakenError):
        cal.create(make_appointment())


def test_backend_selection_requires_settings(settings) -> None:
    from pathlib import Path

    from universal_agent.tools import clinic
    from universal_agent.tools.registry import ToolContext

    clinic._BACKENDS.clear()
    google = settings.model_copy(update={"calendar_backend": "google"})
    ctx = ToolContext("clinic-example", Path(settings.agents_dir) / "clinic-example", google)
    with pytest.raises(ValueError, match="GOOGLE_CALENDAR_ID"):
        clinic.get_backend(ctx)
