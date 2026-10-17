# PawPal+ (Module 2 Project)

You are building **PawPal+**, a Streamlit app that helps a pet owner plan care tasks for their pet.

## Scenario

A busy pet owner needs help staying consistent with pet care. They want an assistant that can:

- Track pet care tasks (walks, feeding, meds, enrichment, grooming, etc.)
- Consider constraints (time available, priority, owner preferences)
- Produce a daily plan and explain why it chose that plan

Your job is to design the system first (UML), then implement the logic in Python, then connect it to the Streamlit UI.

## What you will build

Your final app should:

- Let a user enter basic owner + pet info
- Let a user add/edit tasks (duration + priority at minimum)
- Generate a daily schedule/plan based on constraints and priorities
- Display the plan clearly (and ideally explain the reasoning)
- Include tests for the most important scheduling behaviors

## Getting started

### Setup

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### Suggested workflow

1. Read the scenario carefully and identify requirements and edge cases.
2. Draft a UML diagram (classes, attributes, methods, relationships).
3. Convert UML into Python class stubs (no logic yet).
4. Implement scheduling logic in small increments.
5. Add tests to verify key behaviors.
6. Connect your logic to the Streamlit UI in `app.py`.
7. Refine UML so it matches what you actually built.

## 🧩 How PawPal+ works

PawPal+ is built around four classes in `pawpal_system.py`:

- **Owner**: the person. Stores contact details, daily limits (minutes available for pet
  care, waking hours, and preferred task types), and their pets. Pet names must be unique.
- **Pet**: one animal (name, species, breed, age, weight) and its list of care tasks.
  Tasks can be added, edited, or removed, and exact duplicates are refused.
- **Task**: one care item, like a 30-minute walk at 07:30 on a given day. It has a type,
  duration, priority, how often it repeats, and whether it's done.
- **Scheduler**: the "brain." It keeps no tasks of its own. It asks the Owner for every
  pet's tasks through `get_all_tasks()`, keeps the ones due on the chosen day, and sorts
  them by time.

**How data flows:** Owner → Pets → Tasks, and Scheduler → `owner.get_all_tasks()` →
today's schedule. Because the Scheduler always goes through the Owner, it works across
all pets at once, not just one.

The Scheduler uses the owner's daily limits to build a plan: it picks what fits in the
owner's time and hours, ranks by priority and preferences, and explains every task it
planned or skipped (see **📐 Smarter Scheduling**).

## 🖥️ Sample Output
```
PawPal+ for Jordan (Mochi, Luna) - Friday, October 16, 2026
Available: 90 min | Hours: 07:00-21:00 | Prefers: walk

5. Today's plan
===============
Time   Pet    Task              Type        Duration  Priority
-----  -----  ----------------  ----------  --------  --------
07:30  Mochi  Morning walk      walk          30 min  HIGH
07:30  Luna   Breakfast         feeding        5 min  HIGH
08:00  Luna   Thyroid pill      medication     5 min  HIGH
12:00  Mochi  Brush coat        grooming      10 min  MEDIUM
18:00  Mochi  Evening walk      walk          30 min  HIGH
19:30  Luna   Feather toy play  enrichment    10 min  LOW
-----  -----  ----------------  ----------  --------  --------
6 tasks, 90 min total
Minutes used: 90 of 90 available

6. Skipped tasks
================
Time   Pet    Task           Type        Duration  Priority
-----  -----  -------------  ----------  --------  --------
13:00  Mochi  Puzzle feeder  enrichment    20 min  MEDIUM
16:00  Mochi  Bath           grooming      40 min  MEDIUM
20:45  Luna   Nail trim      grooming      20 min  LOW
-----  -----  -------------  ----------  --------  --------
3 tasks, 80 min total
```

## 🧪 Testing PawPal+

```bash
python -m pytest        # run the suite
python -m pytest -v     # see each test by name
```

**56 tests, all passing.** The suite covers validation (time format, owner hours and
time budget, duplicate pets and tasks, safe edits that leave the original unchanged),
sorting and filtering across pets, conflict warnings (completed tasks ignored), daily
and weekly recurrence (including month/year rollover and no duplicate copies), and every
daily-planner rule: time budget, priority, preferred types, waking hours, the medication
rule, and skip-then-fit.

**Confidence: ★★★★☆.** Every scheduling rule has a test, including the edge cases right
at its boundaries. One star off because the suite covers scheduling only: the Streamlit
UI is tested by hand, and the Health Tracker and Food Marketplace get their tests when
they're built.

**Known limitations** (by design, and tested as such): conflicts are flagged only for the
exact same date and time; a recurring task's next copy is created only when the current
one is marked complete; overnight hours (e.g. 22:00–06:00) aren't supported.

Sample test output:
```
platform win32 -- Python 3.13.14, pytest-9.1.1, pluggy-1.6.0
collected 56 items

tests\test_pawpal.py ........................................................ [100%]

============================== 56 passed in 0.32s ==============================
```

## 📐 Smarter Scheduling

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | `Scheduler.sort_by_time()`, `Scheduler.sort_by_priority()` | By "HH:MM" time, or by priority (HIGH → LOW), then the owner's preferred task types, then time. Uses a rank table, not the priority text, so MEDIUM correctly comes before LOW. |
| Filtering | `Scheduler.filter_tasks()`, `Scheduler.build_daily_plan()`, `Scheduler.skipped_tasks()` | Filter by pet and/or done status across all pets. The daily plan skips tasks outside the owner's hours or that don't fit the time left, and keeps trying smaller tasks after a skip. |
| Conflict handling | `Scheduler.detect_conflicts()` | Warns (never crashes) when two tasks, for the same pet or different pets, share the same date and time. Exact time matches only; overlapping durations are a planned improvement. |
| Recurring tasks | `Scheduler.mark_task_complete()`, `Task.mark_complete()`, `Task.next_occurrence()` | Completing a daily task creates tomorrow's copy; weekly adds 7 days. If the copy already exists it's reused, never duplicated. |
| Plan explanations | `Scheduler.explain_plan()` | One plain-English line per task saying why it was planned or skipped, including when the medication rule overrode the owner's hours or time budget. |

**Medication rule:** medication is always planned, even outside the owner's hours or over
the time budget, and the explanation says so.

**Priority scheduling example** (`python main.py`, section 2):

```
Time   Pet    Task              Type        Duration  Priority
-----  -----  ----------------  ----------  --------  --------
07:30  Mochi  Morning walk      walk          30 min  HIGH
18:00  Mochi  Evening walk      walk          30 min  HIGH
07:30  Luna   Breakfast         feeding        5 min  HIGH
08:00  Luna   Thyroid pill      medication     5 min  HIGH
12:00  Mochi  Brush coat        grooming      10 min  MEDIUM
13:00  Mochi  Puzzle feeder     enrichment    20 min  MEDIUM
16:00  Mochi  Bath              grooming      40 min  MEDIUM
19:30  Luna   Feather toy play  enrichment    10 min  LOW
20:45  Luna   Nail trim         grooming      20 min  LOW
```

**Daily plan explanations** (90 minutes available, walks preferred):

```
- 07:30 Morning walk (Mochi, 30 min): planned. High priority, you prefer walks.
- 07:30 Breakfast (Luna, 5 min): planned. High priority.
- 08:00 Thyroid pill (Luna, 5 min): planned. Medication, always kept (health first).
- 12:00 Brush coat (Mochi, 10 min): planned. Medium priority.
- 13:00 Puzzle feeder (Mochi, 20 min): skipped. Not enough time left (needs 20 min, 10 min left).
- 16:00 Bath (Mochi, 40 min): skipped. Not enough time left (needs 40 min, 10 min left).
- 18:00 Evening walk (Mochi, 30 min): planned. High priority, you prefer walks.
- 19:30 Feather toy play (Luna, 10 min): planned. Low priority.
- 20:45 Nail trim (Luna, 20 min): skipped. Would run past your hours (ends 21:05).
```

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
