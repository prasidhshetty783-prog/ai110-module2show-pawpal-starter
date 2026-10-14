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

The owner's daily limits are stored now and will drive the daily planner, which picks
what fits in the owner's time and explains what it skipped.

## 🖥️ Sample Output

```
PawPal+ for Jordan (Mochi, Luna)

Today's Schedule - Wednesday, October 14, 2026
==================================================
Time   Pet    Task              Duration  Priority
-----  -----  ----------------  --------  --------
07:00  Luna   Breakfast            5 min  HIGH
07:30  Mochi  Morning walk        30 min  HIGH
12:00  Mochi  Brush coat          10 min  MEDIUM
18:00  Mochi  Evening walk        30 min  HIGH
19:30  Luna   Feather toy play    15 min  LOW
-----  -----  ----------------  --------  --------
5 tasks, 90 min total
```

## 🧪 Testing PawPal+

```bash
# Run the full test suite:
pytest

# Run with coverage:
pytest --cov
```

Sample test output:

```

```

## 📐 Smarter Scheduling

> Fill in once you've implemented scheduling logic.

| Feature | Method(s) | Notes |
|---------|-----------|-------|
| Task sorting | | e.g., by priority, duration |
| Filtering | | e.g., skip tasks if time runs out |
| Conflict handling | | e.g., overlapping time slots |
| Recurring tasks | | e.g., daily vs. weekly |

## 📸 Demo Walkthrough

Describe your app in numbered steps so a reader can follow along without watching a video:

1. <!-- Describe this step -->
2. <!-- Describe this step -->
3. <!-- Describe this step -->
4. <!-- Describe this step -->
5. <!-- Add more steps as needed -->

**Screenshot or video** *(optional)*: <!-- Insert a screenshot or link to a demo video here -->
