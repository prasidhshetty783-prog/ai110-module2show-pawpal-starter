# PawPal+ — rules for Claude

CodePath AI110, Project 2. A pet care app in Python: owners, pets, care tasks, a
scheduler, a simulated health tracker, and a simulated food marketplace.
I am the lead architect. You are my coding assistant. Work one phase at a time and
do only what I ask in the current prompt.

## Files
- `pawpal_system.py` — ALL backend classes (the logic layer). No Streamlit, no print().
- `main.py` — CLI demo. Prints everything the logic layer can do.
- `app.py` — Streamlit UI only. Imports from `pawpal_system.py`.
- `tests/test_pawpal.py` — pytest suite.
- `diagrams/uml.mmd` — the design. Source of truth for classes and methods.
- `README.md`, `reflection.md`, `ai_interactions.md` — I write these. Draft only when asked.

## Design rules
- Build only the classes, attributes, and methods in `diagrams/uml.mmd`
  (15 classes + 5 enums). Do not add, rename, or remove a class or public method
  without asking. If a change is needed, tell me the exact `uml.mmd` edit.
- Use `@dataclass` where the UML says `<<dataclass>>`. Lists use `field(default_factory=list)`.
- Enums use lowercase string values: `Priority` = "low" / "medium" / "high"
  (matches the dropdown in app.py). Same style for Frequency, TaskType, Severity, OrderStatus.
- `Task.time` is 24-hour, zero-padded "HH:MM". Validate in `__post_init__`; raise ValueError on bad input.
- `Pet.add_task()` sets `task.pet_name`.
- Scheduler gets tasks ONLY through `owner.get_all_tasks()`. Never read `pet.tasks` inside Scheduler.
- Recurrence: `Task.mark_complete()` sets completed and returns `next_occurrence()`
  (DAILY +1 day, WEEKLY +7 days, via timedelta) or None for ONCE.
  `Scheduler.mark_task_complete()` adds the new task to the right pet.
- `detect_conflicts()` returns warning strings and never raises. It checks exact
  same date + time only (a documented tradeoff).
## Daily plan (the README scenario: track tasks, respect constraints, explain the plan)
- Task types cover walks, feeding, meds, enrichment, grooming, appointments, deliveries
  (`TaskType`). Every task has a type, a duration, and a priority.
- Owner constraints and preferences live on Owner:
  - `available_minutes`: how much care time the owner has that day (default 120)
  - `day_start` / `day_end`: the owner's waking window, "HH:MM" (default "07:00"–"21:00")
  - `preferred_types`: task types the owner wants first when time is tight
- `Scheduler.build_daily_plan(day)` picks the plan, in this order:
  1. Only that day's incomplete tasks, and only times inside day_start–day_end.
  2. MEDICATION tasks are always kept, even if they go over budget (health first).
  3. The rest are ranked by priority (HIGH first), then preferred type, then time.
  4. Add tasks while the total duration fits `available_minutes`; the rest are skipped.
  5. Return the chosen tasks sorted by time.
- `Scheduler.skipped_tasks(day)` returns what didn't make the plan.
- `Scheduler.explain_plan(day)` returns one plain-English line per task, both chosen and
  skipped, naming the real reason: priority, preferred type, medication rule, outside
  the owner's hours, or "not enough time left (needs X min, Y min left)".

## Health Tracker (simulated, no real device)
- `SmartCollar.read_vitals()` makes plausible readings with `random.Random(self.seed)`,
  so the same seed always gives the same readings.
- Keep a `VITAL_RANGES` dict in `pawpal_system.py`:
  - dog: heart rate 60–140 bpm, temperature 38.3–39.2 °C, breathing 10–35/min, SpO2 ≥ 95%
  - cat: heart rate 140–220 bpm, temperature 38.1–39.2 °C, breathing 20–30/min, SpO2 ≥ 95%
  - any other species: track readings, no alerts
- `check_alerts()` returns readable strings. Anywhere alerts are shown (CLI and UI),
  also show: "Not veterinary advice. Contact your vet if you are worried."
- `Medication.to_tasks()` makes one MEDICATION task per time in `times`, priority HIGH.

## Food Marketplace (simulated, no real store)
- `SAMPLE_CATALOG` in `pawpal_system.py`: about 12 products with FICTIONAL brand names
  only, dog and cat, varied price, rating, `supports` conditions, and `allergens`.
- Recommendations: hard-exclude wrong species and any allergen in the pet's
  `health.allergies`. Then score the rest. `explain_recommendation()` must list exactly
  the factors `score()` used, nothing invented.
- `MockPayment.charge()` never asks for or stores card details. It returns True when amount > 0.
- `Cart.checkout()` raises ValueError on an empty cart. Otherwise it charges, creates an
  Order (delivery = placed_on + 3 days), appends it to `owner.orders`, and clears the cart.
- `Order.to_delivery_task()` makes a DELIVERY task on the delivery date.

## Code style
- Python 3.10+, type hints everywhere, a 1-line docstring on every public method, PEP 8.
- `pawpal_system.py` uses the standard library only. Allowed project dependencies:
  streamlit, pytest, tabulate (add tabulate to requirements.txt when we start using it).
- Return data from the logic layer. Formatting and printing happen in `main.py` and `app.py`.

## Tests
- Run with `python -m pytest` (not plain `pytest`, no `--cov`).
- Use fixed dates like `date(2026, 10, 15)`. Never `date.today()` in tests.
- Seed every SmartCollar in tests.
- Every new public method gets at least one test.

## Streamlit
- Keep one Owner in `st.session_state["owner"]`. Create it only if it is missing.
- Sidebar: owner info (name, email, address), owner constraints and preferences
  (available minutes, day start, day end, preferred task types as a multiselect),
  add-pet form, and the Save button.
- Add-task form: pet dropdown (from owner.pets), description, task type (walk, feeding,
  medication, enrichment, grooming, appointment), time, duration, priority, frequency.
  Users can also edit or remove an existing task (the README asks for add AND edit).
- Final layout: three tabs, Schedule | Health | Shop.
  - Schedule tab: "Build today's plan" shows the chosen tasks in a table, total minutes
    used vs available, the skipped tasks with their reasons, explain_plan() for every
    task, and one st.warning per conflict.
- Show results with `st.table`, `st.success`, and `st.warning`.
- Run with `streamlit run app.py`.

## How to work with me
- For changes that touch more than one file, list the files and your plan before editing.
- Never run `git commit` or `git push`. When I ask, suggest a conventional commit
  message (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
- When I ask for a review, point out real problems. Don't just agree with me.
- If you are unsure what I want, ask one question instead of guessing.
- Environment: Windows + PowerShell. venv at `.venv`
  (activate with `.\.venv\Scripts\Activate.ps1`).
