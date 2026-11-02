"""Clinic scheduling tools used by ``agents/clinic-example``.

Configuration comes from ``agents/<agent>/clinic.yaml`` (services, opening hours, timezone). The calendar backend is
chosen with ``CALENDAR_BACKEND``: ``local`` (JSON file, default) or ``google`` (Google Calendar).

Safety properties:

* Booking and cancelling are ``write`` tools, so they wait for human approval.
* Prices and durations come from ``clinic.yaml``, never from the model.
* Slots are re-checked at booking time; a race returns an error instead of a double booking.
* Cancelling requires the phone number the appointment was booked with.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from functools import cache
from pathlib import Path

from langchain_core.tools import BaseTool, StructuredTool

from ..config import Settings
from .registry import ToolContext, register_tool
from .scheduling import (
    Appointment,
    CalendarBackend,
    ClinicConfig,
    LocalCalendar,
    SlotTakenError,
    free_slots,
    load_clinic_config,
    normalize_phone,
)


def now() -> datetime:
    """Current time. Tests monkeypatch this."""
    return datetime.now(UTC)


@cache
def _config(agent_dir: Path) -> ClinicConfig:
    return load_clinic_config(agent_dir / "clinic.yaml")


_BACKENDS: dict[tuple[str, str], CalendarBackend] = {}


def get_backend(ctx: ToolContext) -> CalendarBackend:
    """One backend per agent, created on first use."""
    settings: Settings = ctx.settings
    key = (ctx.agent_name, str(settings.data_dir))
    if key not in _BACKENDS:
        if settings.calendar_backend == "google":
            from .google_calendar import GoogleCalendar, build_service

            if not settings.google_calendar_id or not settings.google_credentials_file:
                raise ValueError("CALENDAR_BACKEND=google needs GOOGLE_CALENDAR_ID and GOOGLE_CREDENTIALS_FILE")
            service = build_service(settings.google_credentials_file)
            _BACKENDS[key] = GoogleCalendar(service, settings.google_calendar_id, _config(ctx.agent_dir).timezone)
        else:
            _BACKENDS[key] = LocalCalendar(settings.data_dir / f"{ctx.agent_name}-appointments.json")
    return _BACKENDS[key]


def _fmt(value: datetime, config: ClinicConfig) -> str:
    return value.astimezone(config.tz).strftime("%Y-%m-%d %H:%M")


def _parse_local(value: str, config: ClinicConfig) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace(" ", "T"))
    return parsed.replace(tzinfo=config.tz) if parsed.tzinfo is None else parsed


@register_tool("clinic_info", risk="read", description="Clinic services, prices, hours and current local time.")
def _clinic_info(ctx: ToolContext) -> BaseTool:
    def clinic_info() -> str:
        """Return the clinic's services (id, duration, price), opening hours and today's local date and time.
        Call it at the start of a scheduling conversation and whenever you need a service id or today's date."""
        config = _config(ctx.agent_dir)
        lines = [f"Now: {_fmt(now(), config)} ({config.timezone}, {now().astimezone(config.tz).strftime('%A')})", "Services:"]
        for s in config.services:
            price = f", price {s.price:.2f}" if s.price is not None else ""
            lines.append(f"- {s.id}: {s.name} ({s.duration_minutes} min{price}) {s.description}".rstrip())
        lines.append("Opening hours: " + "; ".join(f"{d} {', '.join(r)}" for d, r in config.opening_hours.items() if r))
        lines.append(f"Bookings from {config.min_notice_hours:g}h ahead up to {config.booking_window_days} days ahead.")
        return "\n".join(lines)

    return StructuredTool.from_function(clinic_info)


@register_tool("find_available_slots", risk="read", description="Free appointment times for a service on a date.")
def _find_available_slots(ctx: ToolContext) -> BaseTool:
    def find_available_slots(service_id: str, day: str) -> str:
        """List free start times for a service on a date (YYYY-MM-DD, clinic local time).
        If there are none, try the next days before telling the patient there is no availability."""
        config = _config(ctx.agent_dir)
        try:
            service = config.service(service_id)
            target = date.fromisoformat(day)
        except ValueError as exc:
            return f"error: {exc}"
        range_start = datetime.combine(target, datetime.min.time(), config.tz)
        busy = get_backend(ctx).busy(range_start, range_start + timedelta(days=1))
        slots = free_slots(config, service, target, busy, now())
        if not slots:
            return f"No free slots for {service.name} on {day}."
        return f"Free slots for {service.name} on {day}: " + ", ".join(s.astimezone(config.tz).strftime("%H:%M") for s in slots)

    return StructuredTool.from_function(find_available_slots)


@register_tool("book_appointment", risk="write", description="Book an appointment (needs approval).")
def _book_appointment(ctx: ToolContext) -> BaseTool:
    def book_appointment(service_id: str, start: str, patient_name: str, patient_phone: str, notes: str = "") -> str:
        """Book an appointment. `start` is 'YYYY-MM-DD HH:MM' in clinic local time and must come from
        find_available_slots. Confirm service, date, time, name and phone with the patient before calling."""
        config = _config(ctx.agent_dir)
        try:
            service = config.service(service_id)
            begin = _parse_local(start, config)
            phone = normalize_phone(patient_phone)
        except ValueError as exc:
            return f"error: {exc}"
        if not patient_name.strip():
            return "error: patient_name is required"
        range_start = datetime.combine(begin.astimezone(config.tz).date(), datetime.min.time(), config.tz)
        backend = get_backend(ctx)
        valid = free_slots(
            config, service, begin.astimezone(config.tz).date(), backend.busy(range_start, range_start + timedelta(days=1)), now()
        )
        if begin not in valid:
            return "error: that time is not available. Call find_available_slots again and offer the patient other times."
        appointment = Appointment(
            id="",
            service_id=service.id,
            service_name=service.name,
            start=begin,
            end=begin + timedelta(minutes=service.duration_minutes),
            patient_name=patient_name.strip()[:100],
            patient_phone=phone,
            notes=notes.strip()[:500],
        )
        try:
            appointment_id = backend.create(appointment)
        except SlotTakenError:
            return "error: that time was just taken. Call find_available_slots again."
        return f"Booked {service.name} on {_fmt(begin, config)} for {appointment.patient_name}. Appointment id: {appointment_id}."

    return StructuredTool.from_function(book_appointment)


@register_tool("find_my_appointments", risk="read", description="Upcoming appointments for a phone number.")
def _find_my_appointments(ctx: ToolContext) -> BaseTool:
    def find_my_appointments(patient_phone: str) -> str:
        """List the patient's upcoming appointments by the phone number used when booking."""
        config = _config(ctx.agent_dir)
        try:
            phone = normalize_phone(patient_phone)
        except ValueError as exc:
            return f"error: {exc}"
        items = get_backend(ctx).find_by_phone(phone, now())
        if not items:
            return "No upcoming appointments for this phone number."
        return "\n".join(f"- {a.id}: {a.service_name} on {_fmt(a.start, config)} ({a.patient_name})" for a in items)

    return StructuredTool.from_function(find_my_appointments)


@register_tool("cancel_appointment", risk="write", description="Cancel an appointment (needs approval).")
def _cancel_appointment(ctx: ToolContext) -> BaseTool:
    def cancel_appointment(appointment_id: str, patient_phone: str) -> str:
        """Cancel an appointment. Requires the id (from find_my_appointments) and the phone used to book it.
        Confirm with the patient before calling."""
        config = _config(ctx.agent_dir)
        backend = get_backend(ctx)
        try:
            phone = normalize_phone(patient_phone)
        except ValueError as exc:
            return f"error: {exc}"
        appointment = backend.get(appointment_id.strip())
        if appointment is None or appointment.patient_phone != phone:
            return "error: no appointment with this id for this phone number."
        backend.cancel(appointment.id)
        return f"Cancelled {appointment.service_name} on {_fmt(appointment.start, config)}."

    return StructuredTool.from_function(cancel_appointment)
