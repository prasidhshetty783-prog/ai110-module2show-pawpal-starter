"""Tests for the PawPal+ logic layer."""

import json
import re
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

import pytest

from pawpal_system import (
    SAMPLE_CATALOG,
    VITAL_RANGES,
    Cart,
    CartItem,
    FoodProduct,
    Frequency,
    HealthProfile,
    HealthReading,
    Marketplace,
    Medication,
    MockPayment,
    Order,
    OrderStatus,
    Owner,
    Pet,
    Priority,
    Scheduler,
    Severity,
    SmartCollar,
    SymptomEntry,
    Task,
    TaskType,
)

DAY = date(2026, 10, 15)


class Home(NamedTuple):
    """One owner with two pets and a scheduler, shared by most tests."""

    owner: Owner
    mochi: Pet
    luna: Pet
    scheduler: Scheduler


@pytest.fixture
def home() -> Home:
    """Jordan (120 min, 07:00 to 21:00) with Mochi the dog and Luna the cat, no tasks yet."""
    owner = Owner("Jordan", available_minutes=120, day_start="07:00", day_end="21:00")
    mochi = Pet("Mochi", "dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    luna = Pet("Luna", "cat", "Tabby", age_years=5, weight_kg=4.2)
    owner.add_pet(mochi)
    owner.add_pet(luna)
    return Home(owner, mochi, luna, Scheduler(owner))


def make_task(
    description: str,
    time: str,
    *,
    day: date = DAY,
    task_type: TaskType = TaskType.WALK,
    priority: Priority = Priority.MEDIUM,
    duration: int = 15,
    frequency: Frequency = Frequency.ONCE,
    completed: bool = False,
) -> Task:
    """Build a task with sensible defaults so each test states only what matters."""
    return Task(
        description,
        time,
        day,
        task_type,
        frequency=frequency,
        priority=priority,
        duration_minutes=duration,
        completed=completed,
    )


# ---------------------------------------------------------------------------
# Existing basics
# ---------------------------------------------------------------------------

def test_mark_complete_sets_completed_true() -> None:
    """mark_complete() flips a new task from not done to done."""
    task = Task("Morning walk", "07:30", DAY, TaskType.WALK)
    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_add_task_increases_task_count_by_one() -> None:
    """add_task() adds exactly one task to the pet."""
    pet = Pet("Mochi", "dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    before = len(pet.get_tasks())

    pet.add_task(Task("Breakfast", "08:00", DAY, TaskType.FEEDING))

    assert len(pet.get_tasks()) == before + 1


# ---------------------------------------------------------------------------
# Owner and Pet rules
# ---------------------------------------------------------------------------

def test_add_pet_rejects_same_name_in_any_case(home: Home) -> None:
    """A second pet called "mochi" is rejected because "Mochi" already exists."""
    with pytest.raises(ValueError):
        home.owner.add_pet(Pet("mochi", "dog", "Corgi", age_years=2, weight_kg=12.0))

    assert len(home.owner.pets) == 2


def test_add_task_rejects_exact_duplicate_but_allows_another_day(home: Home) -> None:
    """Same description, time, and date is a duplicate; a different date is not."""
    home.mochi.add_task(make_task("Walk", "08:00"))

    with pytest.raises(ValueError):
        home.mochi.add_task(make_task("Walk", "08:00"))
    home.mochi.add_task(make_task("Walk", "08:00", day=DAY + timedelta(days=1)))

    assert len(home.mochi.get_tasks()) == 2


def test_pet_with_no_tasks_gives_empty_plan_and_no_conflicts(home: Home) -> None:
    """With no tasks at all, the plan, skipped list, explanation, and conflicts are empty."""
    assert home.scheduler.build_daily_plan(DAY) == []
    assert home.scheduler.skipped_tasks(DAY) == []
    assert home.scheduler.explain_plan(DAY) == []
    assert home.scheduler.detect_conflicts(DAY) == []


# ---------------------------------------------------------------------------
# 1. Sorting
# ---------------------------------------------------------------------------

def test_sort_by_time_orders_earliest_first(home: Home) -> None:
    """Tasks come back in HH:MM order regardless of the order they were given."""
    late, early, middle = make_task("C", "10:00"), make_task("A", "07:00"), make_task("B", "08:30")

    assert home.scheduler.sort_by_time([late, early, middle]) == [early, middle, late]


def test_sort_by_priority_is_high_medium_low_not_alphabetical(home: Home) -> None:
    """MEDIUM must come before LOW, even though "low" < "medium" alphabetically."""
    low = make_task("Low", "08:00", priority=Priority.LOW)
    high = make_task("High", "09:00", priority=Priority.HIGH)
    medium = make_task("Medium", "10:00", priority=Priority.MEDIUM)

    assert home.scheduler.sort_by_priority([low, high, medium]) == [high, medium, low]


def test_sort_by_priority_breaks_ties_by_preferred_type_then_time(home: Home) -> None:
    """Equal priority: first preferred type, then second, then unlisted types by time."""
    home.owner.preferred_types = [TaskType.FEEDING, TaskType.WALK]
    groom_late = make_task("Brush", "07:00", task_type=TaskType.GROOMING)
    walk = make_task("Walk", "09:00", task_type=TaskType.WALK)
    feed = make_task("Dinner", "10:00", task_type=TaskType.FEEDING)
    groom_early = make_task("Nails", "06:00", task_type=TaskType.GROOMING)

    result = home.scheduler.sort_by_priority([groom_late, walk, feed, groom_early])

    assert result == [feed, walk, groom_early, groom_late]


def test_sorting_returns_new_list_and_leaves_input_alone(home: Home) -> None:
    """Both sorts return a new list; the caller's list keeps its original order."""
    tasks = [make_task("B", "09:00"), make_task("A", "08:00")]
    original = list(tasks)

    by_time = home.scheduler.sort_by_time(tasks)
    by_priority = home.scheduler.sort_by_priority(tasks)

    assert tasks == original
    assert by_time is not tasks and by_priority is not tasks


# ---------------------------------------------------------------------------
# 2. Filtering
# ---------------------------------------------------------------------------

def test_filter_with_no_arguments_returns_every_task(home: Home) -> None:
    """None for both filters means no filtering at all."""
    home.mochi.add_task(make_task("Walk", "08:00"))
    home.luna.add_task(make_task("Feed", "09:00", completed=True))

    assert len(home.scheduler.filter_tasks()) == 2


def test_filter_by_pet_name_ignores_case(home: Home) -> None:
    """"mochi" matches Mochi's tasks and nothing of Luna's."""
    walk = make_task("Walk", "08:00")
    home.mochi.add_task(walk)
    home.luna.add_task(make_task("Feed", "09:00"))

    assert home.scheduler.filter_tasks(pet_name="mochi") == [walk]


def test_filter_by_pet_and_completed_together(home: Home) -> None:
    """Both filters apply at once: Mochi's pending tasks only."""
    pending = make_task("Walk", "08:00")
    home.mochi.add_task(pending)
    home.mochi.add_task(make_task("Feed", "09:00", completed=True))
    home.luna.add_task(make_task("Play", "10:00"))

    assert home.scheduler.filter_tasks(pet_name="Mochi", completed=False) == [pending]


def test_filter_unknown_pet_returns_empty_list(home: Home) -> None:
    """Filtering on a pet that doesn't exist returns [] instead of raising."""
    home.mochi.add_task(make_task("Walk", "08:00"))

    assert home.scheduler.filter_tasks(pet_name="Rex") == []


# ---------------------------------------------------------------------------
# 3. Recurrence
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("start", "frequency", "expected"),
    [
        (DAY, Frequency.DAILY, date(2026, 10, 16)),
        (DAY, Frequency.WEEKLY, date(2026, 10, 22)),
        (date(2026, 10, 31), Frequency.DAILY, date(2026, 11, 1)),
        (date(2026, 12, 29), Frequency.WEEKLY, date(2027, 1, 5)),
    ],
)
def test_next_occurrence_due_date(
    home: Home, start: date, frequency: Frequency, expected: date
) -> None:
    """DAILY adds 1 day and WEEKLY adds 7, across month and year boundaries."""
    home.mochi.add_task(make_task("Walk", "08:00", day=start, frequency=frequency))

    upcoming = home.scheduler.mark_task_complete("Mochi", "Walk", "08:00")

    assert upcoming is not None
    assert upcoming.due_date == expected


def test_next_occurrence_is_a_pending_copy_on_the_same_pet(home: Home) -> None:
    """The new task keeps priority and duration, starts incomplete, and lives on Mochi."""
    original = make_task(
        "Walk", "08:00", frequency=Frequency.DAILY, priority=Priority.HIGH, duration=40
    )
    home.mochi.add_task(original)

    upcoming = home.scheduler.mark_task_complete("Mochi", "Walk", "08:00")

    assert upcoming is not None and upcoming is not original
    assert original.completed is True
    assert upcoming.completed is False
    assert upcoming.priority is Priority.HIGH
    assert upcoming.duration_minutes == 40
    assert upcoming.pet_name == "Mochi"
    assert upcoming in home.mochi.get_tasks()
    assert home.luna.get_tasks() == []


def test_completing_one_time_task_returns_none_and_adds_nothing(home: Home) -> None:
    """A ONCE task is marked done, but no follow-up task is created."""
    vet = make_task("Vet visit", "10:00", task_type=TaskType.APPOINTMENT)
    home.mochi.add_task(vet)

    assert home.scheduler.mark_task_complete("Mochi", "Vet visit", "10:00") is None
    assert vet.completed is True
    assert len(home.mochi.get_tasks()) == 1


def test_existing_next_occurrence_is_returned_not_copied(home: Home) -> None:
    """If tomorrow's copy already exists, that same task comes back and no copy is added."""
    tomorrow = make_task("Walk", "08:00", day=DAY + timedelta(days=1), frequency=Frequency.DAILY)
    home.mochi.add_task(make_task("Walk", "08:00", frequency=Frequency.DAILY))
    home.mochi.add_task(tomorrow)

    upcoming = home.scheduler.mark_task_complete("Mochi", "Walk", "08:00")

    assert upcoming is tomorrow
    assert len(home.mochi.get_tasks()) == 2


def test_completing_twice_works_on_earliest_incomplete_each_time(home: Home) -> None:
    """The first call completes today's walk; the second completes tomorrow's."""
    today = make_task("Walk", "08:00", frequency=Frequency.DAILY)
    home.mochi.add_task(today)

    tomorrow = home.scheduler.mark_task_complete("Mochi", "Walk", "08:00")
    day_after = home.scheduler.mark_task_complete("Mochi", "Walk", "08:00")

    assert tomorrow is not None and day_after is not None
    assert today.completed and tomorrow.completed
    assert day_after.completed is False
    assert day_after.due_date == DAY + timedelta(days=2)
    assert len(home.mochi.get_tasks()) == 3


def test_mark_task_complete_accepts_any_case_pet_name(home: Home) -> None:
    """"mochi" finds Mochi, matching how get_pet() works."""
    walk = make_task("Walk", "08:00")
    home.mochi.add_task(walk)

    home.scheduler.mark_task_complete("mochi", "Walk", "08:00")

    assert walk.completed is True


@pytest.mark.parametrize(
    ("pet_name", "description", "time"),
    [("Rex", "Walk", "08:00"), ("Mochi", "Swim", "08:00"), ("Mochi", "Walk", "09:00")],
)
def test_mark_task_complete_with_no_match_returns_none(
    home: Home, pet_name: str, description: str, time: str
) -> None:
    """Unknown pet, wrong description, or wrong time returns None and never raises."""
    walk = make_task("Walk", "08:00", frequency=Frequency.DAILY)
    home.mochi.add_task(walk)

    assert home.scheduler.mark_task_complete(pet_name, description, time) is None
    assert walk.completed is False


# ---------------------------------------------------------------------------
# 4. Conflict detection
# ---------------------------------------------------------------------------

def test_two_pets_at_same_time_give_one_warning(home: Home) -> None:
    """One clashing pair gives exactly one warning naming both pets and the time."""
    home.mochi.add_task(make_task("Walk", "08:00"))
    home.luna.add_task(make_task("Feed", "08:00"))

    warnings = home.scheduler.detect_conflicts(DAY)

    assert len(warnings) == 1
    assert "08:00" in warnings[0]
    assert "Mochi" in warnings[0] and "Luna" in warnings[0]


def test_three_tasks_at_same_time_give_three_warnings(home: Home) -> None:
    """Three tasks at one time make three pairs, so three warnings."""
    home.mochi.add_task(make_task("Walk", "08:00"))
    home.mochi.add_task(make_task("Pill", "08:00", task_type=TaskType.MEDICATION))
    home.luna.add_task(make_task("Feed", "08:00"))

    assert len(home.scheduler.detect_conflicts(DAY)) == 3


def test_same_pet_two_tasks_at_same_time_is_a_conflict(home: Home) -> None:
    """One pet can't do two things at once either."""
    home.mochi.add_task(make_task("Walk", "08:00"))
    home.mochi.add_task(make_task("Brush", "08:00", task_type=TaskType.GROOMING))

    assert len(home.scheduler.detect_conflicts(DAY)) == 1


def test_same_time_on_different_days_is_not_a_conflict(home: Home) -> None:
    """Only tasks on the requested day are compared."""
    home.mochi.add_task(make_task("Walk", "08:00"))
    home.luna.add_task(make_task("Feed", "08:00", day=DAY + timedelta(days=1)))

    assert home.scheduler.detect_conflicts(DAY) == []


def test_completed_task_does_not_conflict_with_pending_one(home: Home) -> None:
    """A finished 08:00 walk can't clash with a pending 08:00 feeding."""
    home.mochi.add_task(make_task("Walk", "08:00", completed=True))
    home.luna.add_task(make_task("Feed", "08:00"))

    assert home.scheduler.detect_conflicts(DAY) == []


# ---------------------------------------------------------------------------
# 5. Daily planner
# ---------------------------------------------------------------------------

def test_plan_keeps_everything_that_fits_sorted_by_time(home: Home) -> None:
    """Under budget and inside hours: every task is planned, earliest first."""
    dinner = make_task("Dinner", "18:00", task_type=TaskType.FEEDING)
    walk = make_task("Walk", "08:00", duration=30)
    play = make_task("Play", "12:00", task_type=TaskType.ENRICHMENT)
    home.mochi.add_task(dinner)
    home.mochi.add_task(walk)
    home.luna.add_task(play)

    assert home.scheduler.build_daily_plan(DAY) == [walk, play, dinner]
    assert home.scheduler.skipped_tasks(DAY) == []


def test_plan_splits_todays_incomplete_tasks_into_chosen_and_skipped(home: Home) -> None:
    """Chosen + skipped is exactly today's pending tasks, no overlap, one explanation each."""
    home.owner.available_minutes = 60
    walk = make_task("Walk", "08:00", priority=Priority.HIGH, duration=30)
    groom = make_task("Bath", "10:00", priority=Priority.LOW, duration=45)  # too long
    feed = make_task("Lunch", "12:00", task_type=TaskType.FEEDING)
    late = make_task("Late walk", "20:50", duration=30)  # runs past 21:00
    for task in (walk, groom, feed, late):
        home.mochi.add_task(task)
    home.mochi.add_task(make_task("Breakfast", "09:00", completed=True))
    home.luna.add_task(make_task("Play", "11:00", day=DAY + timedelta(days=1)))

    chosen = home.scheduler.build_daily_plan(DAY)
    skipped = home.scheduler.skipped_tasks(DAY)

    assert set(chosen) | set(skipped) == {walk, groom, feed, late}
    assert set(chosen).isdisjoint(skipped)
    assert chosen == [walk, feed]
    assert len(home.scheduler.explain_plan(DAY)) == len(chosen) + len(skipped)


def test_medication_outside_hours_is_still_planned(home: Home) -> None:
    """A 06:00 pill is before day_start but is kept, and the reason says so."""
    pill = make_task("Pill", "06:00", task_type=TaskType.MEDICATION, duration=5)
    home.mochi.add_task(pill)

    assert home.scheduler.build_daily_plan(DAY) == [pill]
    assert "outside your hours" in home.scheduler.explain_plan(DAY)[0]


def test_medication_over_budget_is_kept_and_later_tasks_are_skipped(home: Home) -> None:
    """A 40-min med on a 30-min budget stays; the walk is skipped with 0 min left."""
    home.owner.available_minutes = 30
    meds = make_task("Insulin", "08:00", task_type=TaskType.MEDICATION, duration=40)
    walk = make_task("Walk", "09:00", duration=10)
    home.mochi.add_task(meds)
    home.mochi.add_task(walk)

    explanations = home.scheduler.explain_plan(DAY)

    assert home.scheduler.build_daily_plan(DAY) == [meds]
    assert home.scheduler.skipped_tasks(DAY) == [walk]
    assert "goes over your available time" in explanations[0]
    assert "needs 10 min, 0 min left" in explanations[1]


@pytest.mark.parametrize(("time", "duration"), [("07:00", 30), ("20:30", 30)])
def test_task_on_the_hours_boundary_is_planned(home: Home, time: str, duration: int) -> None:
    """Starting exactly at day_start, or ending exactly at day_end, still fits."""
    task = make_task("Walk", time, duration=duration)
    home.mochi.add_task(task)

    assert home.scheduler.build_daily_plan(DAY) == [task]


@pytest.mark.parametrize(
    ("time", "duration", "reason"),
    [
        ("20:31", 30, "ends 21:01"),
        ("21:00", 15, "Outside your hours"),
        ("06:59", 15, "Outside your hours"),
    ],
)
def test_task_outside_hours_is_skipped_with_reason(
    home: Home, time: str, duration: int, reason: str
) -> None:
    """One minute past either edge of the owner's window is skipped and explained."""
    task = make_task("Walk", time, duration=duration)
    home.mochi.add_task(task)

    assert home.scheduler.skipped_tasks(DAY) == [task]
    assert reason in home.scheduler.explain_plan(DAY)[0]


def test_greedy_plan_skips_big_task_and_keeps_trying_smaller_ones(home: Home) -> None:
    """60 min: HIGH 50 fits, MEDIUM 30 doesn't, LOW 10 still fits after it."""
    home.owner.available_minutes = 60
    high = make_task("Hike", "09:00", priority=Priority.HIGH, duration=50)
    medium = make_task("Bath", "10:00", priority=Priority.MEDIUM, duration=30)
    low = make_task("Fetch", "11:00", priority=Priority.LOW, duration=10)
    for task in (high, medium, low):
        home.mochi.add_task(task)

    assert home.scheduler.build_daily_plan(DAY) == [high, low]
    assert home.scheduler.skipped_tasks(DAY) == [medium]
    assert "needs 30 min, 10 min left" in home.scheduler.explain_plan(DAY)[1]


def test_skip_reasons_maps_each_skipped_task_to_its_explain_plan_reason(home: Home) -> None:
    """Keys are exactly skipped_tasks(); each reason ends the matching explain_plan() line."""
    home.owner.available_minutes = 40
    walk = make_task("Walk", "08:00", priority=Priority.HIGH, duration=30)  # planned
    bath = make_task("Bath", "10:00", priority=Priority.LOW, duration=20)  # too long
    late = make_task("Late walk", "20:50", duration=30)  # runs past 21:00
    for task in (walk, bath, late):
        home.mochi.add_task(task)

    reasons = home.scheduler.skip_reasons(DAY)
    explanations = home.scheduler.explain_plan(DAY)

    assert list(reasons) == home.scheduler.skipped_tasks(DAY) == [bath, late]
    assert walk not in reasons
    assert reasons[bath] == "Not enough time left (needs 20 min, 10 min left)."
    assert reasons[late] == "Would run past your hours (ends 21:20)."
    assert explanations[1].endswith(reasons[bath])
    assert explanations[2].endswith(reasons[late])


def test_preferred_type_wins_when_time_is_tight(home: Home) -> None:
    """Two equal-priority 30-min tasks, 30 min left: the preferred walk is planned."""
    home.owner.available_minutes = 30
    home.owner.preferred_types = [TaskType.WALK]
    feed = make_task("Feed", "08:00", task_type=TaskType.FEEDING, duration=30)
    walk = make_task("Walk", "09:00", task_type=TaskType.WALK, duration=30)
    home.mochi.add_task(feed)
    home.mochi.add_task(walk)

    assert home.scheduler.build_daily_plan(DAY) == [walk]
    assert home.scheduler.skipped_tasks(DAY) == [feed]


def test_explain_plan_names_priority_preference_and_medication(home: Home) -> None:
    """Each line gives the real reason: medication rule, priority, and preferred type."""
    home.owner.preferred_types = [TaskType.WALK]
    home.mochi.add_task(make_task("Pill", "07:30", task_type=TaskType.MEDICATION, duration=5))
    home.mochi.add_task(make_task("Walk", "08:00", priority=Priority.HIGH))
    home.mochi.add_task(make_task("Feed", "09:00", task_type=TaskType.FEEDING))

    pill_line, walk_line, feed_line = home.scheduler.explain_plan(DAY)

    assert "Medication, always kept" in pill_line
    assert "planned. High priority, you prefer walks." in walk_line
    assert "planned. Medium priority." in feed_line


# ---------------------------------------------------------------------------
# 6. Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_time", ["9:00", "24:00", "07:60", "7:5", "08-00"])
def test_task_rejects_bad_time(bad_time: str) -> None:
    """Task time must be zero-padded 24-hour HH:MM."""
    with pytest.raises(ValueError):
        make_task("Walk", bad_time)


def test_owner_rejects_badly_formatted_hours() -> None:
    """day_start and day_end must be HH:MM too."""
    with pytest.raises(ValueError):
        Owner("Jordan", day_start="7:00")
    with pytest.raises(ValueError):
        Owner("Jordan", day_end="25:00")


@pytest.mark.parametrize(("start", "end"), [("21:00", "07:00"), ("09:00", "09:00")])
def test_owner_rejects_start_not_before_end(start: str, end: str) -> None:
    """Overnight or zero-length windows are not supported."""
    with pytest.raises(ValueError):
        Owner("Jordan", day_start=start, day_end=end)


def test_owner_rejects_negative_minutes_but_allows_zero() -> None:
    """-1 available minutes is invalid; 0 is a real (busy) day."""
    with pytest.raises(ValueError):
        Owner("Jordan", available_minutes=-1)

    assert Owner("Jordan", available_minutes=0).available_minutes == 0


def test_update_task_swaps_in_edited_copy(home: Home) -> None:
    """A valid edit replaces the task and keeps it on the same pet."""
    home.mochi.add_task(make_task("Walk", "08:00"))

    assert home.mochi.update_task("Walk", "08:00", {"time": "08:30", "duration_minutes": 45})

    (edited,) = home.mochi.get_tasks()
    assert edited.time == "08:30"
    assert edited.duration_minutes == 45
    assert edited.pet_name == "Mochi"


@pytest.mark.parametrize(
    "changes",
    [{"time": "25:00"}, {"colour": "red"}, {"time": "09:00"}],
    ids=["invalid-time", "unknown-field", "duplicate"],
)
def test_update_task_rejects_bad_changes_and_keeps_original(home: Home, changes: dict) -> None:
    """Bad time, unknown field, or an edit that duplicates another task raises; nothing changes."""
    original = make_task("Walk", "08:00")
    home.mochi.add_task(original)
    home.mochi.add_task(make_task("Walk", "09:00"))

    with pytest.raises(ValueError):
        home.mochi.update_task("Walk", "08:00", changes)

    assert original in home.mochi.get_tasks()
    assert original.time == "08:00"


def test_update_task_with_no_match_returns_false(home: Home) -> None:
    """Editing a task that doesn't exist returns False and never raises."""
    home.mochi.add_task(make_task("Walk", "08:00"))

    assert home.mochi.update_task("Walk", "10:00", {"duration_minutes": 5}) is False


# ---------------------------------------------------------------------------
# 7. Health Tracker
# ---------------------------------------------------------------------------

def at(hhmm: str, day: date = DAY) -> datetime:
    """A fixed datetime on DAY (or another day) at "HH:MM"."""
    hours, minutes = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hours, minutes)


def normal_dog_reading(when: datetime) -> HealthReading:
    """A reading with every vital inside the dog range."""
    return HealthReading(
        timestamp=when, heart_rate_bpm=100, spo2_percent=98.0, temperature_c=38.7,
        respiratory_rate=20, sleep_score=80, steps=1000, distance_km=0.5, calories_burned=40,
    )


def make_med(times: list[str], **overrides) -> Medication:
    """A daily medication starting on DAY."""
    fields = {"name": "Apoquel", "dose": "16 mg", "times": times, "start_date": DAY}
    return Medication(**(fields | overrides))


def in_range(value: float, low: float, high: float | None) -> bool:
    """True if value is inside [low, high] (no upper limit when high is None)."""
    return value >= low and (high is None or value <= high)


# --- SmartCollar ---

def test_same_seed_gives_same_readings_but_each_reading_differs() -> None:
    """Two collars with one seed match reading for reading; consecutive readings differ."""
    a, b = SmartCollar("A", seed=7), SmartCollar("B", seed=7)
    times = [at("08:00"), at("12:00"), at("18:00")]

    run_a = [a.read_vitals(t) for t in times]
    run_b = [b.read_vitals(t) for t in times]

    assert run_a == run_b
    assert run_a[0] != replace(run_a[1], timestamp=run_a[0].timestamp)
    assert [r.timestamp for r in run_a] == times


def test_each_read_drains_battery_by_one_and_never_below_zero() -> None:
    """Battery drops 1 per reading and stops at 0."""
    collar = SmartCollar("A", seed=1, battery_percent=2)

    collar.read_vitals(at("08:00"))
    assert collar.battery_percent == 1
    collar.read_vitals(at("09:00"))
    collar.read_vitals(at("10:00"))

    assert collar.battery_percent == 0


@pytest.mark.parametrize("species", ["dog", "cat"])
def test_collar_values_are_centred_on_its_species_range(species: str) -> None:
    """Decision 1: a collar's vitals sit inside the normal range of its own species."""
    collar = SmartCollar("A", seed=3, species=species)
    ranges = VITAL_RANGES[species]

    for hour in range(6, 22):
        reading = collar.read_vitals(at(f"{hour:02d}:00"))
        for field_name, (low, high) in ranges.items():
            assert in_range(getattr(reading, field_name), low, high), field_name


def test_seeded_cat_collar_gives_no_cat_alerts() -> None:
    """A cat collar's normal readings never trigger check_alerts("cat")."""
    luna = Pet("Luna", "cat", "Tabby", age_years=5, weight_kg=4.2)
    luna.pair_collar(SmartCollar("CAT-1", seed=42, species="Cat"))

    for hour in range(6, 22):
        luna.sync_collar(at(f"{hour:02d}:00"))
        assert luna.health.check_alerts("cat") == []


def test_unknown_species_collar_uses_dog_centred_values() -> None:
    """Decision 1: a rabbit collar reads like a dog collar, and rabbits get no alerts."""
    rabbit_collar = SmartCollar("R", seed=5, species="rabbit")
    dog_collar = SmartCollar("D", seed=5, species="dog")

    assert rabbit_collar.read_vitals(at("08:00")) == dog_collar.read_vitals(at("08:00"))

    profile = HealthProfile()
    profile.add_reading(replace(normal_dog_reading(at("08:00")), heart_rate_bpm=300))
    assert profile.check_alerts("rabbit") == []


def test_steps_are_running_totals_that_reset_each_day() -> None:
    """Decision 2: steps, distance, and calories only grow during a day, then restart."""
    collar = SmartCollar("A", seed=9)

    day_one = [collar.read_vitals(at(t)) for t in ["08:00", "12:00", "18:00"]]
    next_morning = collar.read_vitals(at("08:00", DAY + timedelta(days=1)))

    steps = [r.steps for r in day_one]
    assert steps == sorted(steps) and steps[0] < steps[-1]
    assert day_one[-1].distance_km > day_one[0].distance_km
    assert day_one[-1].calories_burned > day_one[0].calories_burned
    assert next_morning.steps < day_one[-1].steps


def test_reading_earlier_than_the_last_does_not_lower_steps() -> None:
    """An out-of-order (earlier) reading adds no steps; totals never go down."""
    collar = SmartCollar("A", seed=9)
    evening = collar.read_vitals(at("18:00"))

    morning = collar.read_vitals(at("08:00"))

    assert morning.steps == evening.steps


# --- Pet: pairing and syncing ---

def test_pair_collar_marks_it_paired_and_stores_it(home: Home) -> None:
    """Pairing sets is_paired and attaches the collar to the pet."""
    collar = SmartCollar("DOG-1", seed=1)

    home.mochi.pair_collar(collar)

    assert collar.is_paired is True
    assert home.mochi.collar is collar


def test_pair_collar_rejects_an_already_paired_collar(home: Home) -> None:
    """A collar paired to one pet can't be paired to another."""
    collar = SmartCollar("DOG-1", seed=1)
    home.mochi.pair_collar(collar)
    rex = Pet("Rex", "dog", "Boxer", age_years=4, weight_kg=30.0)

    with pytest.raises(ValueError):
        rex.pair_collar(collar)

    assert rex.collar is None


def test_pair_collar_rejects_second_collar_on_same_pet(home: Home) -> None:
    """Decision 3: a pet that already wears a collar can't take another one."""
    first = SmartCollar("DOG-1", seed=1)
    second = SmartCollar("DOG-2", seed=2)
    home.mochi.pair_collar(first)

    with pytest.raises(ValueError):
        home.mochi.pair_collar(second)

    assert home.mochi.collar is first
    assert second.is_paired is False


def test_pair_collar_rejects_collar_for_another_species(home: Home) -> None:
    """Decision 1: a dog collar can't be paired with a cat."""
    collar = SmartCollar("DOG-1", seed=1, species="dog")

    with pytest.raises(ValueError):
        home.luna.pair_collar(collar)

    assert collar.is_paired is False
    assert home.luna.collar is None


def test_sync_collar_without_collar_returns_none(home: Home) -> None:
    """No paired collar means nothing to read."""
    assert home.mochi.sync_collar(at("08:00")) is None
    assert home.mochi.health.readings == []


def test_sync_collar_stores_and_returns_the_reading(home: Home) -> None:
    """A sync reads the collar and saves the reading on the pet's health profile."""
    home.mochi.pair_collar(SmartCollar("DOG-1", seed=1))

    reading = home.mochi.sync_collar(at("08:00"))

    assert reading is not None
    assert home.mochi.health.readings == [reading]
    assert reading.timestamp == at("08:00")


# --- Medication ---

def test_to_tasks_makes_one_high_priority_medication_task_per_time() -> None:
    """Each dose time becomes a HIGH MEDICATION task on the start date with the med's frequency."""
    med = make_med(["08:00", "20:00"], frequency=Frequency.DAILY)

    tasks = med.to_tasks("Mochi")

    assert [t.time for t in tasks] == ["08:00", "20:00"]
    for task in tasks:
        assert task.task_type is TaskType.MEDICATION
        assert task.priority is Priority.HIGH
        assert task.due_date == DAY
        assert task.frequency is Frequency.DAILY
        assert task.pet_name == "Mochi"
        assert "Apoquel" in task.description


def test_medication_tasks_take_five_minutes_each() -> None:
    """Decision 4: every dose is a 5 minute task."""
    tasks = make_med(["08:00", "14:00", "20:00"]).to_tasks("Mochi")

    assert [t.duration_minutes for t in tasks] == [5, 5, 5]


def test_medication_rejects_empty_times() -> None:
    """Decision 5: a medication with no dose times is an error."""
    with pytest.raises(ValueError):
        make_med([])


@pytest.mark.parametrize("bad_time", ["8:00", "24:00", "noon"])
def test_medication_rejects_bad_time(bad_time: str) -> None:
    """Every dose time must be HH:MM."""
    with pytest.raises(ValueError):
        make_med(["08:00", bad_time])


def test_medication_keeps_its_own_copy_of_times() -> None:
    """Changing the caller's list later doesn't change the medication."""
    times = ["08:00"]
    med = make_med(times)

    times.append("20:00")

    assert med.times == ["08:00"]


def test_pet_add_medication_stores_med_and_schedules_reminders(home: Home) -> None:
    """add_medication records the med and its reminders reach the daily plan."""
    med = make_med(["08:00", "20:00"])

    home.mochi.add_medication(med)

    assert home.mochi.health.medications == [med]
    assert [t.time for t in home.mochi.get_tasks()] == ["08:00", "20:00"]
    planned = home.scheduler.build_daily_plan(DAY)
    assert [t.task_type for t in planned] == [TaskType.MEDICATION, TaskType.MEDICATION]


def test_add_medication_with_duplicate_second_dose_adds_nothing(home: Home) -> None:
    """If any dose duplicates an existing task, neither the med nor any dose is added."""
    home.mochi.add_medication(make_med(["20:00"]))
    before = home.mochi.get_tasks()

    with pytest.raises(ValueError):
        home.mochi.add_medication(make_med(["08:00", "20:00"]))

    assert len(home.mochi.health.medications) == 1
    assert home.mochi.get_tasks() == before


def test_add_medication_with_repeated_time_adds_nothing(home: Home) -> None:
    """The same time listed twice in one medication is caught before anything is added."""
    with pytest.raises(ValueError):
        home.mochi.add_medication(make_med(["08:00", "08:00"]))

    assert home.mochi.health.medications == []
    assert home.mochi.get_tasks() == []


# --- HealthProfile ---

def test_profile_add_methods_store_entries() -> None:
    """add_reading, add_medication, and log_symptom each store what they're given."""
    profile = HealthProfile()
    reading = normal_dog_reading(at("08:00"))
    med = make_med(["08:00"])
    symptom = SymptomEntry(DAY, "Itchy ears", Severity.MILD)

    profile.add_reading(reading)
    profile.add_medication(med)
    profile.log_symptom(symptom)

    assert profile.readings == [reading]
    assert profile.medications == [med]
    assert profile.symptoms == [symptom]


def test_profile_keeps_its_own_copy_of_lists() -> None:
    """Lists passed to the constructor are copied."""
    allergies = ["chicken"]
    profile = HealthProfile(allergies=allergies)

    allergies.append("beef")

    assert profile.allergies == ["chicken"]


def test_latest_reading_is_none_with_no_readings() -> None:
    """An empty profile has no latest reading."""
    assert HealthProfile().latest_reading() is None


def test_latest_reading_goes_by_timestamp_not_insertion_order() -> None:
    """A reading added later but timestamped earlier is not the latest."""
    profile = HealthProfile()
    evening = normal_dog_reading(at("18:00"))
    profile.add_reading(evening)
    profile.add_reading(normal_dog_reading(at("08:00")))

    assert profile.latest_reading() is evening


def test_check_alerts_with_no_readings_is_empty() -> None:
    """No readings means no alerts."""
    assert HealthProfile().check_alerts("dog") == []


def test_check_alerts_names_each_out_of_range_vital() -> None:
    """High heart rate and low SpO2 each produce one readable alert; species case is ignored."""
    profile = HealthProfile()
    profile.add_reading(
        replace(normal_dog_reading(at("08:00")), heart_rate_bpm=152, spo2_percent=92.5)
    )

    alerts = profile.check_alerts("Dog")

    assert len(alerts) == 2
    assert any("Heart rate 152 bpm is above" in a and "60 to 140" in a for a in alerts)
    assert any("SpO2 92.5% is below" in a for a in alerts)


def test_check_alerts_uses_only_the_latest_reading() -> None:
    """An old bad reading doesn't alert once a newer normal one exists."""
    profile = HealthProfile()
    profile.add_reading(replace(normal_dog_reading(at("08:00")), temperature_c=40.1))
    profile.add_reading(normal_dog_reading(at("09:00")))

    assert profile.check_alerts("dog") == []


def test_daily_summary_with_no_readings() -> None:
    """A day with no readings has zero totals and None averages."""
    summary = HealthProfile().daily_summary(DAY)

    assert summary["readings"] == 0
    assert summary["avg_heart_rate"] is None
    assert summary["avg_spo2"] is None
    assert summary["avg_temperature"] is None
    assert summary["avg_respiratory_rate"] is None
    assert summary["latest_sleep_score"] is None
    assert summary["total_steps"] == 0
    assert summary["symptoms"] == 0


def test_daily_summary_uses_that_day_only_and_latest_totals() -> None:
    """Decision 2: averages cover that day; totals come from the day's latest reading, not a sum."""
    profile = HealthProfile()
    base = normal_dog_reading(at("08:00"))
    profile.add_reading(replace(base, timestamp=at("18:00"), heart_rate_bpm=110,
                                steps=6000, distance_km=3.0, calories_burned=240,
                                sleep_score=70))
    profile.add_reading(replace(base, heart_rate_bpm=90, steps=1000))
    profile.add_reading(replace(base, timestamp=at("08:00", DAY - timedelta(days=1)),
                                heart_rate_bpm=200, steps=9999))
    profile.log_symptom(SymptomEntry(DAY, "Limping", Severity.MODERATE))
    profile.log_symptom(SymptomEntry(DAY - timedelta(days=1), "Sneezing", Severity.MILD))

    summary = profile.daily_summary(DAY)

    assert summary["readings"] == 2
    assert summary["avg_heart_rate"] == 100.0
    assert summary["total_steps"] == 6000
    assert summary["total_distance_km"] == 3.0
    assert summary["total_calories"] == 240
    assert summary["latest_sleep_score"] == 70
    assert summary["symptoms"] == 1


# --- Food Marketplace: products and catalog ---

# The "(+1.80)" points at the end of each explain_recommendation() line.
POINTS = re.compile(r"\(([+-]\d+\.\d{2})\)$")


def make_product(
    product_id: str = "P1",
    *,
    species: str = "dog",
    life_stage: str = "adult",
    price: float = 40.0,
    rating: float = 4.0,
    supports: tuple[str, ...] = (),
    allergens: tuple[str, ...] = (),
    brand: str = "Test Brand",
    name: str = "Test Food",
) -> FoodProduct:
    """Build a product with sensible defaults so each test states only what matters."""
    return FoodProduct(product_id, brand, name, species, life_stage, price, rating, 350,
                       supports=list(supports), allergens=list(allergens))


def explained_points(lines: list[str]) -> list[float]:
    """Pull the points out of each explain_recommendation() line."""
    points = []
    for line in lines:
        match = POINTS.search(line)
        assert match is not None, f"no points in {line!r}"
        points.append(float(match.group(1)))
    return points


def test_sample_catalog_prices_are_positive_and_under_the_price_ceiling() -> None:
    """The price score assumes every price is below $100."""
    assert all(0 < p.price < 100 for p in SAMPLE_CATALOG)


def test_sample_catalog_has_unique_ids_and_both_species() -> None:
    """About 12 products, each with its own id, for dogs and cats."""
    ids = [p.product_id for p in SAMPLE_CATALOG]
    assert len(ids) == len(set(ids)) >= 10
    assert {p.species for p in SAMPLE_CATALOG} == {"dog", "cat"}


def test_food_product_stores_species_lowercase() -> None:
    """'Dog' and 'dog' match, as with Pet.species."""
    assert make_product(species="Dog").species == "dog"


def test_food_product_rejects_unknown_life_stage() -> None:
    """life_stage must be young, adult, senior, or all."""
    with pytest.raises(ValueError):
        make_product(life_stage="puppy")


def test_food_product_keeps_its_own_copy_of_lists() -> None:
    """Changing the list passed in does not change the product."""
    supports = ["digestion"]
    product = FoodProduct("P1", "B", "N", "dog", "adult", 10.0, 4.0, 300, supports=supports)
    supports.append("joint health")
    assert product.supports == ["digestion"]


def test_marketplace_keeps_its_own_copy_of_catalog() -> None:
    """Adding to the list passed in does not change the marketplace."""
    catalog = [make_product("A")]
    market = Marketplace(catalog)
    catalog.append(make_product("B"))
    assert [p.product_id for p in market.catalog] == ["A"]


def test_search_matches_brand_or_name_for_one_species_ignoring_case() -> None:
    """Search filters by species, then looks for the query in brand or name."""
    lamb = make_product("A", brand="Barkley Farms", name="Lamb Adult")
    senior = make_product("B", brand="Tailwind", name="Lamb Senior")
    cat = make_product("C", species="cat", brand="Barkley Farms", name="Lamb Cat")
    market = Marketplace([lamb, senior, cat])

    assert market.search("DOG", "barkley") == [lamb]
    assert market.search("dog", "LAMB") == [lamb, senior]
    assert market.search("dog", "") == [lamb, senior]


# --- Food Marketplace: recommendations ---

def test_recommend_never_includes_allergens_or_wrong_species(home: Home) -> None:
    """Hard exclusions: only dog food, and nothing with an allergen Mochi has (any case)."""
    home.mochi.health.allergies.append("Chicken")
    market = Marketplace(SAMPLE_CATALOG)
    assert any(p.species == "dog" and "chicken" in p.allergens for p in SAMPLE_CATALOG)

    recommended = market.recommend_for(home.mochi, len(SAMPLE_CATALOG))

    expected = {p.product_id for p in SAMPLE_CATALOG
                if p.species == "dog" and "chicken" not in p.allergens}
    assert {p.product_id for p in recommended} == expected


def test_excluded_product_scores_zero_and_explains_why(home: Home) -> None:
    """An unsafe product scores 0.0 and its only explanation is the exclusion."""
    home.mochi.health.allergies.append("beef")
    market = Marketplace()
    beefy = make_product(allergens=("beef",))
    cat_food = make_product(species="cat")

    assert market.score(beefy, home.mochi) == 0.0
    [reason] = market.explain_recommendation(beefy, home.mochi)
    assert "beef" in reason and "allergic" in reason

    assert market.score(cat_food, home.mochi) == 0.0
    [reason] = market.explain_recommendation(cat_food, home.mochi)
    assert "cat" in reason


def test_senior_pet_ranks_senior_food_above_adult_food_when_all_else_ties() -> None:
    """Same price and rating: the life-stage match decides, not catalog order or id."""
    senior_pet = Pet("Biscuit", "dog", "Beagle", age_years=9, weight_kg=12.0)
    adult_food = make_product("A", life_stage="adult")
    senior_food = make_product("S", life_stage="senior")
    market = Marketplace([adult_food, senior_food])

    assert market.recommend_for(senior_pet, 2) == [senior_food, adult_food]
    gap = market.score(senior_food, senior_pet) - market.score(adult_food, senior_pet)
    assert gap == pytest.approx(2.0)


def test_explain_lists_exactly_the_factors_score_used(home: Home) -> None:
    """Every factor appears once, and the explained points add up to the score."""
    home.mochi.health.conditions.extend(["joint health", "Sensitive Skin"])
    market = Marketplace()
    product = make_product(life_stage="all", rating=4.0, price=40.0,
                           supports=("sensitive skin", "joint health", "digestion"))

    lines = market.explain_recommendation(product, home.mochi)

    assert [line.split(" (")[0] for line in lines] == [
        "Supports joint health, one of Mochi's conditions",
        "Supports sensitive skin, one of Mochi's conditions",
        "Suitable for all life stages",
        "Rated 4/5",
        "Price $40.00",
    ]
    assert explained_points(lines) == [3.0, 3.0, 2.0, 1.6, 0.6]
    assert sum(explained_points(lines)) == pytest.approx(market.score(product, home.mochi))


def test_explain_leaves_out_factors_that_did_not_apply(home: Home) -> None:
    """No condition and no life-stage match: only rating and price are listed."""
    market = Marketplace()
    product = make_product(life_stage="senior", supports=("joint health",))

    lines = market.explain_recommendation(product, home.mochi)

    assert len(lines) == 2
    assert lines[0].startswith("Rated") and lines[1].startswith("Price")
    assert sum(explained_points(lines)) == pytest.approx(market.score(product, home.mochi))


@pytest.mark.parametrize("age, stage", [(0.99, "young"), (1, "adult"), (6.99, "adult"),
                                        (7, "senior")])
def test_life_stage_comes_from_age(age: float, stage: str) -> None:
    """Under 1 is young, 1 to under 7 is adult, 7 and over is senior."""
    pet = Pet("Pip", "dog", "Mixed", age_years=age, weight_kg=8.0)
    lines = Marketplace().explain_recommendation(make_product(life_stage=stage), pet)
    assert lines[0] == f"Made for {stage} pets, and Pip is {stage} (+2.00)"


def test_cheaper_product_scores_higher_when_all_else_ties(home: Home) -> None:
    """Price is a scored factor: lower price, higher score."""
    market = Marketplace()
    cheap, pricey = make_product(price=20.0), make_product(price=80.0)
    assert market.score(cheap, home.mochi) > market.score(pricey, home.mochi)


def test_recommend_for_returns_at_most_top_n(home: Home) -> None:
    """top_n caps the list; zero or less gives an empty list."""
    market = Marketplace(SAMPLE_CATALOG)
    assert len(market.recommend_for(home.mochi, 2)) == 2
    assert market.recommend_for(home.mochi, 0) == []


def test_compare_includes_kcal_and_skips_unknown_ids() -> None:
    """compare() keeps the requested order, skips unknown ids, and shows kcal_per_cup."""
    rows = Marketplace(SAMPLE_CATALOG).compare(["C03", "NOPE", "D01"])

    assert [row["product_id"] for row in rows] == ["C03", "D01"]
    assert rows[0]["kcal_per_cup"] == 350
    assert rows[1]["brand"] == "Barkley Farms"


# --- Food Marketplace: cart, payment, orders ---

class DecliningPayment(MockPayment):
    """A payment that always fails, to test checkout's declined-charge path."""

    def charge(self, amount: float) -> bool:
        """Decline every charge."""
        return False


def test_cart_item_subtotal_is_price_times_quantity() -> None:
    """Subtotal multiplies price by quantity."""
    assert CartItem(make_product(price=12.5), 3).subtotal() == 37.5


def test_add_item_merges_quantity_for_same_product() -> None:
    """Adding a product already in the cart raises its quantity instead of adding a line."""
    cart = Cart()
    product = make_product()
    cart.add_item(product, 1)
    cart.add_item(product, 2)

    assert len(cart.items) == 1
    assert cart.items[0].quantity == 3


@pytest.mark.parametrize("quantity", [0, -1])
def test_add_item_rejects_quantity_below_one(quantity: int) -> None:
    """Quantity must be at least 1; nothing is added."""
    cart = Cart()
    with pytest.raises(ValueError):
        cart.add_item(make_product(), quantity)
    assert cart.items == []


def test_remove_item_reports_whether_it_was_there() -> None:
    """remove_item returns True once, then False."""
    cart = Cart()
    cart.add_item(make_product("A"), 1)
    assert cart.remove_item("A") is True
    assert cart.remove_item("A") is False


def test_cart_total_sums_subtotals() -> None:
    """2 x $10.99 + 1 x $4.50 = $26.48."""
    cart = Cart()
    cart.add_item(make_product("A", price=10.99), 2)
    cart.add_item(make_product("B", price=4.50), 1)
    assert cart.total() == 26.48


def test_clear_empties_the_cart() -> None:
    """clear() removes every item."""
    cart = Cart()
    cart.add_item(make_product(), 1)
    cart.clear()
    assert cart.items == []
    assert cart.total() == 0


def test_mock_payment_charges_only_positive_amounts() -> None:
    """The fake processor accepts any amount above zero."""
    payment = MockPayment()
    assert payment.charge(10.0) is True
    assert payment.charge(0) is False
    assert payment.charge(-5.0) is False


def test_checkout_raises_on_empty_cart(home: Home) -> None:
    """An empty cart cannot be checked out."""
    with pytest.raises(ValueError):
        home.owner.cart.checkout(home.owner, MockPayment(), "Mochi", DAY)
    assert home.owner.orders == []


def test_checkout_raises_on_unknown_pet_and_changes_nothing(home: Home) -> None:
    """The delivery task needs a real pet; the cart is left as it was."""
    cart = home.owner.cart
    cart.add_item(make_product(), 1)

    with pytest.raises(ValueError):
        cart.checkout(home.owner, MockPayment(), "Rex", DAY)
    assert len(cart.items) == 1
    assert home.owner.orders == []


def test_checkout_raises_on_declined_charge_and_changes_nothing(home: Home) -> None:
    """A declined charge leaves the cart, orders, and pet tasks untouched."""
    cart = home.owner.cart
    cart.add_item(make_product(), 1)

    with pytest.raises(ValueError):
        cart.checkout(home.owner, DecliningPayment(), "Mochi", DAY)
    assert len(cart.items) == 1
    assert home.owner.orders == []
    assert home.mochi.get_tasks() == []


def test_checkout_creates_order_with_delivery_task_and_clears_cart(home: Home) -> None:
    """ORD-0001, delivery in 3 days, a DELIVERY task on the pet, and an empty cart."""
    home.owner.address = "12 Elm Street"
    cart = home.owner.cart
    cart.add_item(make_product(price=25.0), 2)

    order = cart.checkout(home.owner, MockPayment(), "mochi", DAY)  # any case finds Mochi

    assert order.order_id == "ORD-0001"
    assert order.total == 50.0
    assert order.status is OrderStatus.PLACED
    assert order.placed_on == DAY
    assert order.delivery_date == DAY + timedelta(days=3)
    assert order.delivery_address == "12 Elm Street"
    assert home.owner.orders == [order]
    assert cart.items == []

    [delivery] = home.mochi.get_tasks()
    assert delivery.task_type is TaskType.DELIVERY
    assert delivery.due_date == DAY + timedelta(days=3)
    assert delivery.pet_name == "Mochi"
    assert "ORD-0001" in delivery.description


def test_checkout_order_keeps_items_after_cart_cleared(home: Home) -> None:
    """The order holds its own copy of the items, so clearing the cart doesn't empty it."""
    cart = home.owner.cart
    cart.add_item(make_product("A"), 1)

    order = cart.checkout(home.owner, MockPayment(), "Mochi", DAY)

    assert cart.items == []
    assert order.items is not cart.items
    assert [item.product.product_id for item in order.items] == ["A"]


def test_second_checkout_gets_the_next_order_id(home: Home) -> None:
    """Order ids count up from the number of orders placed."""
    cart = home.owner.cart
    cart.add_item(make_product("A"), 1)
    cart.checkout(home.owner, MockPayment(), "Mochi", DAY)
    cart.add_item(make_product("A"), 1)

    second = cart.checkout(home.owner, MockPayment(), "Luna", DAY)

    assert second.order_id == "ORD-0002"
    assert len(home.owner.orders) == 2


def make_order() -> Order:
    """A freshly placed order."""
    return Order(order_id="ORD-0001", total=10.0, placed_on=DAY,
                 delivery_date=DAY + timedelta(days=3), delivery_address="12 Elm Street")


def test_advance_status_goes_placed_shipped_delivered_then_false() -> None:
    """PLACED -> SHIPPED -> DELIVERED, then it stays DELIVERED and returns False."""
    order = make_order()

    assert order.advance_status() is True
    assert order.status is OrderStatus.SHIPPED
    assert order.advance_status() is True
    assert order.status is OrderStatus.DELIVERED
    assert order.advance_status() is False
    assert order.status is OrderStatus.DELIVERED


def test_to_delivery_task_is_a_one_time_delivery_on_the_delivery_date() -> None:
    """The delivery task is due on the delivery date and does not repeat."""
    task = make_order().to_delivery_task("Mochi")

    assert task.task_type is TaskType.DELIVERY
    assert task.due_date == DAY + timedelta(days=3)
    assert task.frequency is Frequency.ONCE
    assert task.pet_name == "Mochi"


# --- Save and load ---

def task_fields(task: Task) -> tuple:
    """Every saved field of a task, for comparing an original with its loaded copy."""
    return (task.pet_name, task.description, task.time, task.due_date, task.task_type,
            task.frequency, task.priority, task.duration_minutes, task.completed)


def save_and_load(owner: Owner, tmp_path: Path) -> Owner:
    """Save an owner to a temp file and load it back."""
    path = tmp_path / "data.json"
    owner.save_to_json(str(path))
    return Owner.load_from_json(str(path))


def test_round_trip_keeps_pets_tasks_preferences_and_constraints(tmp_path: Path) -> None:
    """Pets, every task field (enums, dates, completed), and owner settings survive a reload."""
    owner = Owner("Jordan", email="jordan@example.com", address="12 Elm Street",
                  available_minutes=90, day_start="06:30", day_end="22:00",
                  preferred_types=[TaskType.WALK, TaskType.GROOMING])
    mochi = Pet("Mochi", "dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    luna = Pet("Luna", "cat", "Tabby", age_years=0.5, weight_kg=4.2)
    owner.add_pet(mochi)
    owner.add_pet(luna)
    mochi.add_task(make_task("Morning walk", "07:30", priority=Priority.HIGH, duration=30,
                             frequency=Frequency.DAILY))
    mochi.add_task(make_task("Brush coat", "18:00", task_type=TaskType.GROOMING,
                             priority=Priority.LOW, frequency=Frequency.WEEKLY, completed=True))
    luna.add_task(make_task("Vet visit", "10:00", day=DAY + timedelta(days=2),
                            task_type=TaskType.APPOINTMENT, duration=60))

    loaded = save_and_load(owner, tmp_path)

    assert (loaded.name, loaded.email, loaded.address) == (
        "Jordan", "jordan@example.com", "12 Elm Street")
    assert (loaded.available_minutes, loaded.day_start, loaded.day_end) == (90, "06:30", "22:00")
    assert loaded.preferred_types == [TaskType.WALK, TaskType.GROOMING]
    assert [(p.name, p.species, p.breed, p.age_years, p.weight_kg) for p in loaded.pets] == [
        ("Mochi", "dog", "Shiba Inu", 3, 10.5), ("Luna", "cat", "Tabby", 0.5, 4.2)]
    # Enum members never equal their text, and date never equals str, so this also
    # checks that enums and dates come back as real Enum and date objects.
    assert [task_fields(t) for t in loaded.get_all_tasks()] == [
        task_fields(t) for t in owner.get_all_tasks()]

    saved_walk = json.loads((tmp_path / "data.json").read_text(encoding="utf-8"))[
        "pets"][0]["tasks"][0]
    assert (saved_walk["priority"], saved_walk["frequency"], saved_walk["due_date"]) == (
        "high", "daily", "2026-10-15")


def test_round_trip_keeps_health_data_without_duplicate_reminders(
    home: Home, tmp_path: Path
) -> None:
    """Readings, medications, symptoms, and collar survive; reminder tasks are not doubled."""
    mochi = home.mochi
    mochi.health.conditions.append("joint health")
    mochi.health.allergies.append("chicken")
    mochi.add_medication(Medication(name="Carprofen", dose="25 mg", times=["08:00", "20:00"],
                                    start_date=DAY))
    mochi.health.log_symptom(SymptomEntry(DAY, "Limping on left leg", Severity.MILD))
    mochi.pair_collar(SmartCollar("COL-1", seed=42))
    for hour in (8, 12, 18):
        mochi.sync_collar(datetime(2026, 10, 15, hour, 0))

    loaded = save_and_load(home.owner, tmp_path).get_pet("Mochi")

    assert loaded is not None
    assert loaded.health.conditions == ["joint health"]
    assert loaded.health.allergies == ["chicken"]
    assert loaded.health.medications == mochi.health.medications
    assert loaded.health.symptoms == mochi.health.symptoms
    assert loaded.health.readings == mochi.health.readings
    assert len(loaded.health.readings) == 3
    assert [task_fields(t) for t in loaded.tasks] == [task_fields(t) for t in mochi.tasks]
    assert len([t for t in loaded.tasks if t.task_type is TaskType.MEDICATION]) == 2
    collar = loaded.collar
    assert collar is not None
    assert (collar.device_id, collar.seed, collar.species, collar.battery_percent,
            collar.is_paired) == ("COL-1", 42, "dog", 97, True)


def test_loaded_collar_restarts_from_its_seed(home: Home, tmp_path: Path) -> None:
    """After a load, the collar's next reading matches a brand-new collar with the same seed."""
    home.mochi.pair_collar(SmartCollar("COL-1", seed=42))
    home.mochi.sync_collar(datetime(2026, 10, 15, 8, 0))

    loaded = save_and_load(home.owner, tmp_path).get_pet("Mochi")

    assert loaded is not None and loaded.collar is not None
    at = datetime(2026, 10, 15, 9, 0)
    assert loaded.collar.read_vitals(at) == SmartCollar("COL-2", seed=42).read_vitals(at)


def test_round_trip_keeps_cart_and_orders_and_continues_order_ids(
    home: Home, tmp_path: Path
) -> None:
    """Cart items, orders, status, and dates survive; the next checkout is ORD-0002."""
    owner = home.owner
    owner.address = "12 Elm Street"
    owner.cart.add_item(make_product("P1", price=25.0, supports=("digestion",),
                                     allergens=("chicken",)), 2)
    first = owner.cart.checkout(owner, MockPayment(), "Mochi", DAY)
    first.advance_status()
    owner.cart.add_item(make_product("P2", price=10.0), 3)

    loaded = save_and_load(owner, tmp_path)

    assert [(i.product, i.quantity) for i in loaded.cart.items] == [
        (make_product("P2", price=10.0), 3)]
    [order] = loaded.orders
    assert order == first
    assert order.status is OrderStatus.SHIPPED
    assert (order.placed_on, order.delivery_date) == (DAY, DAY + timedelta(days=3))
    assert [(i.product.product_id, i.quantity) for i in order.items] == [("P1", 2)]

    second = loaded.cart.checkout(loaded, MockPayment(), "Mochi", DAY + timedelta(days=1))
    assert second.order_id == "ORD-0002"


def test_load_from_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    """Loading a path that doesn't exist raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        Owner.load_from_json(str(tmp_path / "missing.json"))


def test_loaded_owner_builds_the_same_daily_plan(home: Home, tmp_path: Path) -> None:
    """The reloaded owner's plan, skipped tasks, and explanations match the original's."""
    home.owner.preferred_types = [TaskType.ENRICHMENT]
    home.mochi.add_medication(Medication(name="Carprofen", dose="25 mg", times=["06:00"],
                                         start_date=DAY))
    home.mochi.add_task(make_task("Long walk", "07:30", priority=Priority.HIGH, duration=60))
    home.mochi.add_task(make_task("Puzzle toy", "11:00", task_type=TaskType.ENRICHMENT,
                                  duration=50))
    home.mochi.add_task(make_task("Brush coat", "15:00", task_type=TaskType.GROOMING,
                                  priority=Priority.LOW, duration=45))
    home.mochi.add_task(make_task("Late walk", "20:50", duration=30))
    home.luna.add_task(make_task("Breakfast", "08:00", task_type=TaskType.FEEDING,
                                 priority=Priority.HIGH, duration=10))
    home.luna.add_task(make_task("Done already", "09:00", completed=True))

    loaded = Scheduler(save_and_load(home.owner, tmp_path))

    def keys(tasks: list[Task]) -> list[tuple[str, str, str]]:
        """Identify tasks across the two owners by pet, description, and time."""
        return [(t.pet_name, t.description, t.time) for t in tasks]

    assert home.scheduler.skipped_tasks(DAY)  # the plan really had to leave something out
    assert keys(loaded.build_daily_plan(DAY)) == keys(home.scheduler.build_daily_plan(DAY))
    assert keys(loaded.skipped_tasks(DAY)) == keys(home.scheduler.skipped_tasks(DAY))
    assert loaded.explain_plan(DAY) == home.scheduler.explain_plan(DAY)
