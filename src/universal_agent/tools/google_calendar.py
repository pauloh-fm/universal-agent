"""Google Calendar backend for the scheduling tools.

Install the optional dependencies with ``uv sync --extra google`` and follow
``docs/integrations/google-calendar.md``. Authentication uses a Google Cloud service account that has been
given access to the clinic calendar ("Make changes to events").
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .scheduling import Appointment, SlotTakenError, overlaps

SCOPES = ["https://www.googleapis.com/auth/calendar.events", "https://www.googleapis.com/auth/calendar.freebusy"]
APP_TAG = "universal-agent"


def build_service(credentials_file: Path) -> Any:
    """Create an authenticated Calendar API client from a service-account JSON key."""
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise RuntimeError("Google Calendar support needs: uv sync --extra google") from exc
    credentials_cls: Any = service_account.Credentials  # google-auth is untyped; Any keeps mypy happy with or without it
    credentials = credentials_cls.from_service_account_file(str(credentials_file), scopes=SCOPES)
    return build("calendar", "v3", credentials=credentials, cache_discovery=False)


class GoogleCalendar:
    """``CalendarBackend`` on top of the Google Calendar API v3.

    Appointment metadata (service, patient phone) is stored in the event's *private extended properties*, which are
    visible only through the API to callers with access to the calendar, and used to look appointments up by phone.
    """

    def __init__(self, service: Any, calendar_id: str, timezone: str) -> None:
        self.service = service
        self.calendar_id = calendar_id
        self.timezone = timezone

    def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        body = {"timeMin": start.isoformat(), "timeMax": end.isoformat(), "items": [{"id": self.calendar_id}]}
        result = self.service.freebusy().query(body=body).execute()
        calendar = result["calendars"][self.calendar_id]
        if calendar.get("errors"):
            raise RuntimeError(f"Google Calendar free/busy error: {calendar['errors']}")
        return [(_parse(b["start"]), _parse(b["end"])) for b in calendar.get("busy", [])]

    def create(self, appointment: Appointment) -> str:
        # Re-check right before writing: another conversation may have taken the slot.
        if any(overlaps(appointment.start, appointment.end, b0, b1) for b0, b1 in self.busy(appointment.start, appointment.end)):
            raise SlotTakenError("slot is no longer available")
        body = {
            "summary": f"{appointment.service_name} - {appointment.patient_name}",
            "description": appointment.notes,
            "start": {"dateTime": appointment.start.isoformat(), "timeZone": self.timezone},
            "end": {"dateTime": appointment.end.isoformat(), "timeZone": self.timezone},
            "extendedProperties": {
                "private": {
                    "app": APP_TAG,
                    "service_id": appointment.service_id,
                    "service_name": appointment.service_name,
                    "patient_name": appointment.patient_name,
                    "patient_phone": appointment.patient_phone,
                }
            },
        }
        event = self.service.events().insert(calendarId=self.calendar_id, body=body).execute()
        return str(event["id"])

    def get(self, appointment_id: str) -> Appointment | None:
        try:
            event = self.service.events().get(calendarId=self.calendar_id, eventId=appointment_id).execute()
        except Exception as exc:  # googleapiclient.errors.HttpError
            if getattr(getattr(exc, "resp", None), "status", None) in (404, 410):
                return None
            raise
        if event.get("status") == "cancelled":
            return None
        return _to_appointment(event)

    def cancel(self, appointment_id: str) -> None:
        self.service.events().delete(calendarId=self.calendar_id, eventId=appointment_id, sendUpdates="none").execute()

    def find_by_phone(self, phone: str, after: datetime) -> list[Appointment]:
        result = (
            self.service.events()
            .list(
                calendarId=self.calendar_id,
                privateExtendedProperty=[f"patient_phone={phone}", f"app={APP_TAG}"],
                timeMin=after.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=20,
            )
            .execute()
        )
        return [a for a in (_to_appointment(e) for e in result.get("items", [])) if a is not None]


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _to_appointment(event: dict[str, Any]) -> Appointment | None:
    props = event.get("extendedProperties", {}).get("private", {})
    if props.get("app") != APP_TAG or "dateTime" not in event.get("start", {}):
        return None
    return Appointment(
        id=event["id"],
        service_id=props.get("service_id", ""),
        service_name=props.get("service_name", event.get("summary", "")),
        start=_parse(event["start"]["dateTime"]),
        end=_parse(event["end"]["dateTime"]),
        patient_name=props.get("patient_name", ""),
        patient_phone=props.get("patient_phone", ""),
        notes=event.get("description", ""),
    )
