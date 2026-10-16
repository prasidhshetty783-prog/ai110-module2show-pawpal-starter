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
  Private helpers (leading underscore) are fine and don't go in the UML.
- Use `@dataclass` where the UML says `<<dataclass>>`. Lists use `field(default_factory=list)`.
  `Pet` and `Task` use `@dataclass(eq=False)` so they compare by identity, not by value.
- Constructors that take a list (catalog, preferred_types, etc.) store a copy: `list(x)`.
- Enums use lowercase string values: `Priority` = "low" / "medium" / "high"
  (matches the dropdown in app.py). Same style for Frequency, TaskType, Severity, OrderStatus.
- Validation (raise ValueError on bad input):
  - `Task.time`, `Owner.day_start`, `Owner.day_end`, and every `Medication.times` entry
    must be 24-hour, zero-padded "HH:MM".
  - `Pet.species` and `FoodProduct.species` are stored lowercase (normalize in
    `__post_init__`), so "Dog" and "dog" match.
- `Owner.add_pet()` raises ValueError if a pet with the same name already exists
  (case-insensitive). Pet names are unique per owner.
- `Pet.add_task()` sets `task.pet_name`, and raises ValueError if the pet already has a
  task with the same description, time, AND due_date (no exact duplicates).
- Task identity: a task is found by pet + description + time. Because a recurring task's
  next occurrence has the same description and time, `remove_task()`, `update_task()`, and
  `mark_task_complete()` act on the earliest-due INCOMPLETE match. If nothing matches they
  return False / None and never raise.
- `Pet.update_task(description, time, changes)` is how tasks get edited: build the edited
  copy with `dataclasses.replace(task, **changes)` (this re-runs validation), check it
  isn't a duplicate, then swap it in. Returns False if no match; raises ValueError for
  invalid values. Never edit task fields directly from the UI.
- Recurrence: `Task.mark_complete()` sets completed and returns `next_occurrence()`
  (DAILY +1 day, WEEKLY +7 days, via timedelta) or None for ONCE.
  `Scheduler.mark_task_complete(pet_name, description, time)` adds the new task to the
  right pet and returns it. If that next occurrence already exists, it does not add a
  copy; it returns the existing task. Returns None for a one-time task or no match.
  It never raises.
- Known limitation (document it in the README): the next occurrence of a recurring task
  is only created when the current one is marked complete.
- Methods that can find nothing return Optional: `get_pet`, `latest_reading`, and
  `sync_collar` (None when no collar is paired).
- `Scheduler.filter_tasks(pet_name=None, completed=None)`: None means "don't filter on this".
- `detect_conflicts()` returns warning strings and never raises. It checks exact
  same date + time only (a documented tradeoff).

## Daily plan (the README scenario: track tasks, respect constraints, explain the plan)
- Task types cover walks, feeding, meds, enrichment, grooming, appointments, deliveries
  (`TaskType`). Every task has a type, a duration, and a priority.
- Owner constraints and preferences live on Owner:
  - `available_minutes`: how much care time the owner has that day (default 120)
  - `day_start` / `day_end`: the owner's waking window, "HH:MM" (default "07:00"–"21:00")
  - `preferred_types`: task types the owner wants first when time is tight
- The plan is computed ONCE by a private helper `Scheduler._plan(day)` that returns
  (chosen, skipped, reasons). `build_daily_plan`, `skipped_tasks`, and `explain_plan`
  all call it, so they can never disagree. Rules, in order:
  1. Only that day's incomplete tasks.
  2. MEDICATION tasks are always kept, even outside the owner's hours or over the time
     budget (health first). Their minutes still count toward the total.
  3. Any other task that starts before day_start OR ends after day_end (start time +
     duration) is skipped ("outside your hours", or "would run past your hours (ends 21:20)").
  4. The rest are ranked by priority (HIGH first), then preferred type, then time.
     Use a private rank table `_PRIORITY_RANK = {HIGH: 0, MEDIUM: 1, LOW: 2}`; never sort
     on the priority text ("high" < "low" < "medium" alphabetically is wrong).
     Preferred-type rank = position in `owner.preferred_types` (first = most preferred;
     types not in the list come after all preferred ones). One shared private sort key
     (`_rank_key`) is used by both `sort_by_priority()` and `_plan()`.
  5. Go down the ranked list: add a task if it fits the minutes left; if it doesn't fit,
     skip it and keep trying the next (smaller) tasks.
  6. Return the chosen tasks sorted by time.
- `Scheduler.explain_plan(day)` returns one plain-English line per task, both chosen and
  skipped, naming the real reason: priority, preferred type, medication rule, outside
  the owner's hours, or "not enough time left (needs X min, Y min left)".

## Health Tracker (simulated, no real device)
- `SmartCollar` creates ONE `random.Random(seed)` in `__init__` and keeps it (as a
  private attribute). Each `read_vitals(at)` call uses it, so a run of readings is
  repeatable from the seed but each reading differs. `at` becomes the reading's timestamp.
  Each read lowers `battery_percent` by 1 (never below 0).
- `Pet.pair_collar(collar)` raises ValueError if the collar is already paired; otherwise
  it sets `collar.is_paired = True` and stores it. `Pet.sync_collar(at)` reads and stores
  a reading in `pet.health`, or returns None if no collar is paired.
- `Pet.add_medication(med)` is how medications get added: it stores the med in
  `pet.health` AND adds every `med.to_tasks(pet.name)` task with `add_task()`. That is
  how medication reminders reach the schedule.
- Keep a `VITAL_RANGES` dict in `pawpal_system.py`:
  - dog: heart rate 60–140 bpm, temperature 38.3–39.2 °C, breathing 10–35/min, SpO2 ≥ 95%
  - cat: heart rate 140–220 bpm, temperature 38.1–39.2 °C, breathing 20–30/min, SpO2 ≥ 95%
  - any other species: track readings, no alerts
- `check_alerts()` returns readable strings. Anywhere alerts are shown (CLI and UI),
  also show: "Not veterinary advice. Contact your vet if you are worried."
- `Medication.to_tasks()` makes one MEDICATION task per time in `times`, priority HIGH.

## Food Marketplace (simulated, no real store)
- `SAMPLE_CATALOG` in `pawpal_system.py`: about 12 products with FICTIONAL brand names
  only, dog and cat, varied price, rating, `supports` conditions, `allergens`, and
  `life_stage` ("young", "adult", "senior", or "all").
- A pet's life stage comes from `age_years`: under 1 = young, 1 to under 7 = adult,
  7 and over = senior.
- Recommendations: hard-exclude wrong species and any allergen in the pet's
  `health.allergies`. Then score the rest: matching health conditions, matching life
  stage (or "all"), rating, and price. `explain_recommendation()` must list exactly
  the factors `score()` used, nothing invented.
- `kcal_per_cup` is shown in `compare()` only; it is not scored.
- `Cart.add_item()`: adding a product already in the cart increases its quantity;
  quantity must be at least 1 (ValueError otherwise).
- `MockPayment.charge()` never asks for or stores card details. It returns True when amount > 0.
- `Cart.checkout(owner, payment, pet_name, today)`:
  - raises ValueError on an empty cart, an unknown pet name, or a declined charge
  - creates the Order with `order_id = f"ORD-{len(owner.orders) + 1:04d}"` (orders are
    never deleted, so IDs stay unique, even after a JSON load), `placed_on = today`,
    `delivery_date = today + 3 days`, and `items=list(self.items)` (a copy, so the cart
    and the order never share a list)
  - appends the Order to `owner.orders`, adds `order.to_delivery_task(pet_name)` to that
    pet, and clears the cart
- `OrderStatus` is PLACED, SHIPPED, DELIVERED (no cancel in this version).
  `Order.advance_status()` moves PLACED → SHIPPED → DELIVERED and returns True; at
  DELIVERED it returns False. It never raises.

## Save and load (stretch)
- Hand-written `to_dict` / `from_dict` helpers (private), standard library `json` only.
  Enums save as their values, `date` / `datetime` as ISO strings.
- After a load, a collar's random generator restarts from its seed (document this).

## Code style
- Python 3.10+, type hints everywhere, a 1-line docstring on every public method, PEP 8.
- `pawpal_system.py` uses the standard library only. Allowed project dependencies:
  streamlit, pytest, tabulate (add tabulate to requirements.txt when we start using it).
- Return data from the logic layer. Formatting and printing happen in `main.py` and `app.py`.
- The logic layer never calls `date.today()` or `datetime.now()`. Dates and times are
  passed in as parameters (`day`, `today`, `at`). Only `main.py` and `app.py` read the clock.

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
  Users can also edit (via `pet.update_task`) or remove an existing task (the README
  asks for add AND edit).
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
