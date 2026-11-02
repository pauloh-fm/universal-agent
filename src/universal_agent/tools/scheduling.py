"""Appointment scheduling: clinic configuration, slot computation and calendar backends.

The logic here is plain Python with no LangChain dependency so it is easy to test. The tools that expose it to an
agent live in ``tools/clinic.py``. Two backends ship with the template:

* ``LocalCalendar`` (default) - appointments in a JSON file under ``DATA_DIR``. Works offline.
* ``GoogleCalendar`` - a real Google Calendar via a service account (``tools/google_calendar.py``).

Select one with ``CALENDAR_BACKEND=local|google``. See ``docs/integrations/google-calendar.md``.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml
from pydantic import BaseModel, Field, field_validator

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_RANGE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)-([01]\d|2[0-3]):([0-5]\d)$")


# --- configuration ---------------------------------------------------------------------


class Service(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,40}$")
    name: str
    duration_minutes: int = Field(ge=5, le=480)
    price: float | None = Field(default=None, ge=0)
    description: str = ""


class ClinicConfig(BaseModel):
    """Contents of ``agents/<name>/clinic.yaml``."""

    timezone: str = "UTC"
    slot_step_minutes: int = Field(default=30, ge=5, le=240)
    min_notice_hours: float = Field(default=2, ge=0)
    booking_window_days: int = Field(default=30, ge=1, le=365)
    opening_hours: dict[str, list[str]]
    closed_dates: list[date] = []
    services: list[Service] = Field(min_length=1)

    @field_validator("timezone")
    @classmethod
    def _valid_tz(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown timezone '{value}'") from exc
        return value

    @field_validator("opening_hours")
    @classmethod
    def _valid_hours(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        for day, ranges in value.items():
            if day not in WEEKDAYS:
                raise ValueError(f"unknown weekday '{day}', use {WEEKDAYS}")
            for item in ranges:
                match = _RANGE.match(item)
                if not match or match.group(1, 2) >= match.group(3, 4):
                    raise ValueError(f"invalid range '{item}', expected HH:MM-HH:MM")
        return value

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def service(self, service_id: str) -> Service:
        for service in self.services:
            if service.id == service_id:
                return service
        raise ValueError(f"unknown service '{service_id}'. Valid ids: {[s.id for s in self.services]}")

    def ranges_for(self, day: date) -> list[tuple[datetime, datetime]]:
        if day in self.closed_dates:
            return []
        out = []
        for item in self.opening_hours.get(WEEKDAYS[day.weekday()], []):
            start_s, end_s = item.split("-")
            start = datetime.combine(day, time.fromisoformat(start_s), self.tz)
            end = datetime.combine(day, time.fromisoformat(end_s), self.tz)
            out.append((start, end))
        return out


def load_clinic_config(path: Path) -> ClinicConfig:
    if not path.is_file():
        raise ValueError(f"missing {path.name} in {path.parent}")
    return ClinicConfig.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})


# --- appointments and backends ---------------------------------------------------------


@dataclass
class Appointment:
    id: str
    service_id: str
    service_name: str
    start: datetime
    end: datetime
    patient_name: str
    patient_phone: str
    notes: str = ""


class CalendarBackend(Protocol):
    """What a calendar must provide. Implement it to plug in any other calendar system."""

    def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        """Busy intervals overlapping [start, end)."""
        ...

    def create(self, appointment: Appointment) -> str:
        """Persist the appointment and return its id."""
        ...

    def get(self, appointment_id: str) -> Appointment | None: ...

    def cancel(self, appointment_id: str) -> None: ...

    def find_by_phone(self, phone: str, after: datetime) -> list[Appointment]: ...


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if not 6 <= len(digits) <= 15:
        raise ValueError("phone must have 6 to 15 digits")
    return digits


def overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    return a_start < b_end and b_start < a_end


class LocalCalendar:
    """JSON-file calendar. Good for development, demos and single-instance deployments."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> list[Appointment]:
        if not self.path.is_file():
            return []
        rows = json.loads(self.path.read_text(encoding="utf-8"))
        return [
            Appointment(**{**row, "start": datetime.fromisoformat(row["start"]), "end": datetime.fromisoformat(row["end"])})
            for row in rows
        ]

    def _save(self, items: list[Appointment]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rows = [{**asdict(a), "start": a.start.isoformat(), "end": a.end.isoformat()} for a in items]
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def busy(self, start: datetime, end: datetime) -> list[tuple[datetime, datetime]]:
        return [(a.start, a.end) for a in self._load() if overlaps(a.start, a.end, start, end)]

    def create(self, appointment: Appointment) -> str:
        with self._lock:
            items = self._load()
            if any(overlaps(a.start, a.end, appointment.start, appointment.end) for a in items):
                raise SlotTakenError("slot is no longer available")
            appointment.id = appointment.id or uuid.uuid4().hex[:8]
            items.append(appointment)
            self._save(items)
            return appointment.id

    def get(self, appointment_id: str) -> Appointment | None:
        return next((a for a in self._load() if a.id == appointment_id), None)

    def cancel(self, appointment_id: str) -> None:
        with self._lock:
            self._save([a for a in self._load() if a.id != appointment_id])

    def find_by_phone(self, phone: str, after: datetime) -> list[Appointment]:
        return sorted((a for a in self._load() if a.patient_phone == phone and a.end > after), key=lambda a: a.start)


class SlotTakenError(Exception):
    """Raised by a backend when the requested time was booked in the meantime."""


# --- availability ----------------------------------------------------------------------


def free_slots(
    config: ClinicConfig, service: Service, day: date, busy: list[tuple[datetime, datetime]], now: datetime
) -> list[datetime]:
    """Start times on ``day`` where ``service`` fits inside opening hours and does not overlap ``busy``."""
    earliest = now + timedelta(hours=config.min_notice_hours)
    latest_day = now.astimezone(config.tz).date() + timedelta(days=config.booking_window_days)
    if day > latest_day:
        return []
    duration = timedelta(minutes=service.duration_minutes)
    step = timedelta(minutes=config.slot_step_minutes)
    out = []
    for range_start, range_end in config.ranges_for(day):
        start = range_start
        while start + duration <= range_end:
            end = start + duration
            if start >= earliest and not any(overlaps(start, end, b0, b1) for b0, b1 in busy):
                out.append(start)
            start += step
    return out
