# Google Calendar integration

Connect `clinic-example` (or any agent using the scheduling tools) to a real Google Calendar.
Appointments booked by the agent become calendar events; events created by staff directly in the calendar
(meetings, vacations, blocks) make those times unavailable.

Time needed: about 15 minutes. Cost: the Google Calendar API is free within its usage quotas.

## How it works

```
patient -> agent -> find_available_slots -> clinic.yaml (opening hours) + Calendar free/busy -> free times
                 -> book_appointment (after approval) -> re-check free/busy -> events.insert
                 -> find_my_appointments -> events.list (private property patient_phone)
                 -> cancel_appointment (after approval) -> events.delete
```

- **Opening hours, services, durations and prices** stay in `agents/clinic-example/clinic.yaml`. The calendar is the
  source of truth only for *what is already taken*.
- **Any** event in the calendar blocks its time, including events not created by the agent. To block a lunch break or
  a day off, just add an event.
- Appointment details (service id, patient name, phone) are stored in the event's
  [private extended properties](https://developers.google.com/calendar/api/guides/extended-properties), used to find
  appointments by phone. Only accounts with access to the calendar can read them.
- The agent authenticates as a **service account**: a robot Google account owned by your Google Cloud project.
  No user needs to log in, and no personal password is involved.

## 1. Create a Google Cloud project and enable the API

1. Open the [Google Cloud console](https://console.cloud.google.com/) with the Google account that will own the
   integration (preferably an organisation account, not a personal one).
2. Project selector (top bar) → **New project**. Name it, e.g. `clinic-agent`. Create and select it.
3. **APIs & Services → Library** → search **Google Calendar API** → **Enable**.

## 2. Create a service account and key

1. **IAM & Admin → Service accounts → Create service account**.
2. Name: `clinic-agent-calendar`. Skip the optional role and user access steps (it needs no project roles).
3. Open the new service account → **Keys → Add key → Create new key → JSON**. A file downloads.
4. Copy the service account **e-mail** (like `clinic-agent-calendar@clinic-agent.iam.gserviceaccount.com`).

> The JSON key is a password. Store it **outside the repository** (e.g. `/etc/universal-agent/google-sa.json`,
> `chmod 600`), or in your platform's secret store. `.gitignore` also ignores `*service-account*.json` and
> `credentials*.json` as a safety net. If a key leaks, delete it in the console and create a new one.

If your organisation blocks key creation (policy `iam.disableServiceAccountKeyCreation`), ask an admin for an
exception for this project, or run the agent on Google Cloud and use the attached service account instead of a key
(see [Without a key file](#without-a-key-file)).

## 3. Create the calendar and share it with the service account

Use a dedicated calendar for appointments rather than a personal one.

1. In [Google Calendar](https://calendar.google.com/), **Other calendars → + → Create new calendar**.
   Name it, e.g. `Clinic appointments`, and set the **time zone** to the clinic's zone.
2. Open the calendar's **Settings and sharing**:
   - **Share with specific people or groups → Add people** → paste the service account e-mail →
     permission **Make changes to events** → Send.
   - Under **Integrate calendar**, copy the **Calendar ID** (like `abc123...@group.calendar.google.com`).
3. Staff who should see the appointments: share the calendar with them as usual.

For multiple professionals, create one calendar per professional and run one agent folder per calendar (copy
`clinic-example`), or extend the tools to take a professional id (see [Extending](#extending)).

## 4. Configure the agent

```bash
uv sync --extra google     # installs google-api-python-client and google-auth (the Docker image already has them)
```

In `.env`:

```dotenv
CALENDAR_BACKEND=google
GOOGLE_CALENDAR_ID=abc123...@group.calendar.google.com
GOOGLE_CREDENTIALS_FILE=/etc/universal-agent/google-sa.json
```

Make sure `timezone` in `agents/clinic-example/clinic.yaml` matches the calendar's time zone, and adjust
`opening_hours`, `closed_dates` and `services` to the clinic.

With Docker, mount the key read-only and point the variable to the mounted path:

```yaml
# compose.yaml (service "agent")
    volumes:
      - /etc/universal-agent/google-sa.json:/run/secrets/google-sa.json:ro
    environment:
      GOOGLE_CREDENTIALS_FILE: /run/secrets/google-sa.json
```

## 5. Test

1. Create a test event in the calendar tomorrow at 10:00-11:00.
2. Run the agent:

   ```bash
   uv run universal-agent chat clinic-example
   ```

   With a real model configured (`LLM_PROVIDER=openai`, see [configuration](../configuration.md)):
   *"I'd like a general consultation tomorrow morning."*
3. Check that 10:00 and 10:30 are **not** offered (blocked by your test event).
4. Choose a time, give a fictitious name and phone, confirm, then approve with `y`.
5. The event appears in Google Calendar as `General consultation - <name>`.
6. Ask *"Which appointments do I have?"* with the same phone, then cancel it; the event disappears.

Without a real model, you can call the backend directly:

```bash
uv run python - <<'EOF'
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from universal_agent.config import get_settings
from universal_agent.tools.google_calendar import GoogleCalendar, build_service

s = get_settings()
cal = GoogleCalendar(build_service(s.google_credentials_file), s.google_calendar_id, "America/New_York")
start = datetime.now(ZoneInfo("America/New_York")).replace(hour=0, minute=0, second=0, microsecond=0)
print(cal.busy(start, start + timedelta(days=2)))   # busy intervals today and tomorrow
EOF
```

## Troubleshooting

| Error | Cause | Fix |
| --- | --- | --- |
| `Google Calendar support needs: uv sync --extra google` | Optional dependencies missing. | `uv sync --extra google`. |
| `CALENDAR_BACKEND=google needs GOOGLE_CALENDAR_ID and GOOGLE_CREDENTIALS_FILE` | Variables not set. | Set both in `.env`. |
| `Google Calendar free/busy error: [{'reason': 'notFound'}]` | Wrong calendar id, or calendar not shared with the service account. | Re-check step 3; sharing can take a minute. |
| `403 ... insufficient permissions` / `requiredAccessLevel` | Shared as "See all event details" only. | Share with **Make changes to events**. |
| `403 accessNotConfigured` | API not enabled in the key's project. | Enable Google Calendar API (step 1) in the same project. |
| `invalid_grant` / `Invalid JWT Signature` | Key deleted or server clock wrong. | Create a new key; sync the clock (NTP). |
| Offered times are shifted by some hours | `clinic.yaml` timezone differs from the calendar's. | Use the same IANA zone in both. |
| Times blocked although the calendar looks empty | Events with "Busy" status on that calendar, or all-day events marked busy. | Set those events to "Free" or remove them. |

## Security notes

- The service account can only access calendars explicitly shared with it.
- Scopes requested: `calendar.events` and `calendar.freebusy`. It cannot change calendar settings or sharing.
- Booking and cancelling are `write` tools: they wait for human approval
  (`REQUIRE_CONFIRMATION_FOR=["write"]`). Keep it that way unless you add other safeguards.
- Cancelling requires the phone number stored on the event, so one patient cannot cancel another's appointment by
  guessing ids.
- Patient phone numbers and names are personal data. Restrict who the calendar is shared with, and follow the data
  protection law that applies to the clinic (e.g. GDPR, HIPAA, LGPD). Health details should not go into event notes.

## Without a key file

When the agent runs on Google Cloud (Cloud Run, GKE, Compute Engine), attach the service account to the workload
and use Application Default Credentials instead of a JSON key. In `tools/google_calendar.py`, replace the
`from_service_account_file` call with:

```python
import google.auth

credentials, _ = google.auth.default(scopes=SCOPES)
```

and leave `GOOGLE_CREDENTIALS_FILE` set to any placeholder (or drop the check in `tools/clinic.py`).

## Using a person's calendar instead (OAuth)

A service account cannot be added to Google Workspace resources the same way as a user in every organisation, and
some clinics prefer the professional's own calendar. In that case use the OAuth "installed app" flow
(`google-auth-oauthlib`): run it once to obtain a refresh token for the professional, store the token as a secret,
and build the client with `google.oauth2.credentials.Credentials`. Everything else in `GoogleCalendar` stays the same.

Google Workspace admins can alternatively grant the service account
[domain-wide delegation](https://support.google.com/a/answer/162106) and impersonate the professional with
`credentials.with_subject("professional@your-domain.com")`.

## Extending

- **Several professionals:** add `calendar_id` to each service (or a `professionals:` list in `clinic.yaml`) and pass
  it to the backend; `find_available_slots` gets a `professional_id` argument.
- **Reminders:** a scheduled job that lists tomorrow's events (`events.list` with `privateExtendedProperty=app=universal-agent`)
  and sends a message through your channel.
- **Other calendars:** implement the `CalendarBackend` protocol in `tools/scheduling.py` (five methods) for
  Microsoft 365 (Graph API), Cal.com, CalDAV or your practice-management system, and select it in `get_backend`.
