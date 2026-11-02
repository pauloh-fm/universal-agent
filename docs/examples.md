# Example agents

Four agents ship with the template. All data in them (names, addresses, phones, prices, orders) is **fictitious**;
replace it with your own.

| Agent | Shows | Tools |
| --- | --- | --- |
| `assistant` | Minimal agent, read-only tools. | `calculator`, `current_time` |
| `support` | Knowledge base answers with citations, ticket creation with approval. | `search_knowledge`, `create_ticket` |
| `clinic-example` | Appointment scheduling with a local or **Google Calendar** backend. | `clinic_info`, `search_knowledge`, `find_available_slots`, `book_appointment`, `find_my_appointments`, `cancel_appointment` |
| `ecommerce-example` | Product search, order placement, tracking and cancellation. | `search_products`, `search_knowledge`, `get_order_status`, `create_order`, `cancel_order`, `create_ticket` |

Delete the ones you do not need (and their tests in `tests/`).

## clinic-example

A receptionist for the fictitious *Example Health Clinic*.

```
agents/clinic-example/
  agent.yaml        tools
  prompt.md         behaviour: scheduling steps, no medical advice, emergency rule
  clinic.yaml       timezone, opening hours, holidays, services (duration, price), booking rules
  knowledge/        about.md, policies.md, preparation.md
src/universal_agent/tools/
  scheduling.py     ClinicConfig, slot computation, CalendarBackend protocol, LocalCalendar
  clinic.py         the six tools
  google_calendar.py  GoogleCalendar backend
```

**Calendar backends**

- `CALENDAR_BACKEND=local` (default): appointments in `DATA_DIR/clinic-example-appointments.json`. Works offline.
- `CALENDAR_BACKEND=google`: a real Google Calendar. Step-by-step setup:
  [Google Calendar integration](integrations/google-calendar.md).
- Anything else: implement `CalendarBackend` (5 methods) and select it in `clinic.get_backend`.

**Guarantees enforced in code, not in the prompt**

- Free times are computed from `clinic.yaml` and the calendar; the model cannot offer a time that is not free.
- `book_appointment` re-validates the slot right before writing, so two conversations cannot double-book.
- Prices and durations come from `clinic.yaml`.
- Booking and cancelling wait for human approval.
- Cancelling requires the phone number stored with the appointment.

**Try it**

```bash
uv run universal-agent chat clinic-example   # with a real model configured in .env
```

> "Hi, I'd like a dermatology appointment next Tuesday afternoon."
> "What should I do before a blood test?"
> "I need to cancel my appointment, my phone is 555 0101."

**Adapting to a real clinic**

1. Edit `clinic.yaml`: timezone, hours, holidays, services.
2. Replace `knowledge/*.md` with the clinic's real information.
3. Rename the folder (and `name:` in `agent.yaml`) and the clinic name in `prompt.md`.
4. Connect Google Calendar or another backend.
5. Decide who approves bookings: staff (default flow), or the patient's own confirmation in your channel UI
   (see [extending](extending.md#channels)).
6. Review the emergency and medical-advice rules with the clinic, and the data protection requirements.

## ecommerce-example

A shopping assistant for the fictitious *Example Outdoor Store*.

```
agents/ecommerce-example/
  agent.yaml
  prompt.md
  catalog.yaml        currency, shipping rules, products (sku, price, stock)
  demo_orders.yaml    two fictitious orders seeded on first run (ORD-1001 shipped, ORD-1002 processing)
  knowledge/          shipping.md, returns.md, payment.md
src/universal_agent/tools/
  ecommerce.py        Catalog, OrderStore, the four tools
```

**Guarantees enforced in code**

- Totals and shipping are computed from `catalog.yaml`; unknown SKUs and quantities above stock are rejected.
- Orders and cancellations wait for approval; only `placed`/`processing` orders can be cancelled.
- Order lookups need the order id **and** the e-mail on the order.
- No payment data in chat: the flow assumes a payment link sent by e-mail.

**Try it**

> "I need a backpack for a weekend hike."
> "What's the status of order ORD-1001? My e-mail is alex@example.com."
> "Cancel ORD-1002, e-mail sam@example.com."

**Adapting to a real store**

Replace `load_catalog()` and `OrderStore` in `tools/ecommerce.py` with calls to your platform's API
(Shopify, WooCommerce, VTEX, Medusa, your own backend). Keep the tool names, arguments and risk levels so the
prompt and tests keep working; update the tests to mock your API client. Create the payment link in `create_order`
through your payment provider and never let the model see card data.
