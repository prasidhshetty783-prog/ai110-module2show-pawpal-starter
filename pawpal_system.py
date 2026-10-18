"""PawPal+ logic layer: owners, pets, tasks, scheduling, health tracking, and a food marketplace.

Built from diagrams/uml.mmd. Core scheduling and the health tracker are implemented;
marketplace methods are still stubs.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from itertools import combinations
from typing import Optional

_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_hhmm(value: str, field_name: str) -> None:
    """Raise ValueError unless value is a zero-padded 24-hour "HH:MM" string."""
    if not isinstance(value, str) or not _HHMM_PATTERN.match(value):
        raise ValueError(f"{field_name} must be 24-hour 'HH:MM' (e.g. '07:30'), got {value!r}")


def _to_minutes(hhmm: str) -> int:
    """Convert a validated "HH:MM" string to minutes after midnight."""
    hours, minutes = hhmm.split(":")
    return int(hours) * 60 + int(minutes)


def _from_minutes(total: int) -> str:
    """Convert minutes after midnight to "HH:MM", wrapping past midnight."""
    hours, minutes = divmod(total % (24 * 60), 60)
    return f"{hours:02d}:{minutes:02d}"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(Enum):
    """How important a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# Sort rank for priorities (lower = more urgent). Never sort on the text values:
# alphabetically "high" < "low" < "medium", which is wrong.
_PRIORITY_RANK: dict[Priority, int] = {Priority.HIGH: 0, Priority.MEDIUM: 1, Priority.LOW: 2}


class Frequency(Enum):
    """How often a task or medication repeats."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


# How far ahead the next occurrence of a recurring task is due. ONCE has no entry.
_RECURRENCE_STEP: dict[Frequency, timedelta] = {
    Frequency.DAILY: timedelta(days=1),
    Frequency.WEEKLY: timedelta(days=7),
}


class TaskType(Enum):
    """The kind of care a task represents."""

    WALK = "walk"
    FEEDING = "feeding"
    MEDICATION = "medication"
    GROOMING = "grooming"
    ENRICHMENT = "enrichment"
    APPOINTMENT = "appointment"
    DELIVERY = "delivery"


# How each task type reads in a plan explanation ("you prefer walks").
_TYPE_LABELS: dict[TaskType, str] = {
    TaskType.WALK: "walks",
    TaskType.FEEDING: "feeding",
    TaskType.MEDICATION: "medication",
    TaskType.GROOMING: "grooming",
    TaskType.ENRICHMENT: "enrichment",
    TaskType.APPOINTMENT: "appointments",
    TaskType.DELIVERY: "deliveries",
}


class Severity(Enum):
    """How serious a logged symptom is."""

    MILD = "mild"
    MODERATE = "moderate"
    SEVERE = "severe"


class OrderStatus(Enum):
    """Where an order is in its lifecycle."""

    PLACED = "placed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"


# ---------------------------------------------------------------------------
# Health Tracker
# ---------------------------------------------------------------------------

# Normal resting vitals per species, keyed by HealthReading field name.
# (low, high); None means no upper limit. Species not listed get no alerts.
VITAL_RANGES: dict[str, dict[str, tuple[float, Optional[float]]]] = {
    "dog": {
        "heart_rate_bpm": (60, 140),
        "temperature_c": (38.3, 39.2),
        "respiratory_rate": (10, 35),
        "spo2_percent": (95, None),
    },
    "cat": {
        "heart_rate_bpm": (140, 220),
        "temperature_c": (38.1, 39.2),
        "respiratory_rate": (20, 30),
        "spo2_percent": (95, None),
    },
}

# How each vital reads in an alert: (label, unit suffix).
_VITAL_LABELS: dict[str, tuple[str, str]] = {
    "heart_rate_bpm": ("Heart rate", " bpm"),
    "temperature_c": ("Temperature", " °C"),
    "respiratory_rate": ("Breathing rate", "/min"),
    "spo2_percent": ("SpO2", "%"),
}

# A collar for a species not in VITAL_RANGES produces values centred on this one.
_FALLBACK_SPECIES = "dog"

# Collar activity model: steps per minute since the last reading, and per-step conversions.
_STEP_RATE: tuple[int, int] = (5, 12)
_KM_PER_STEP = 0.0005
_KCAL_PER_STEP = 0.04

# Every medication reminder takes this long; it counts toward the owner's daily minutes.
_MEDICATION_MINUTES = 5


@dataclass
class HealthReading:
    """One snapshot of vitals and activity from a smart collar."""

    timestamp: datetime
    heart_rate_bpm: int
    spo2_percent: float
    temperature_c: float
    respiratory_rate: int
    sleep_score: int
    steps: int
    distance_km: float
    calories_burned: int


@dataclass(kw_only=True)
class Medication:
    """A medication with a dose and the times of day it is given."""

    name: str
    dose: str
    times: list[str] = field(default_factory=list)
    frequency: Frequency = Frequency.DAILY
    start_date: date

    def __post_init__(self) -> None:
        """Keep a private copy of times and check there is at least one valid "HH:MM"."""
        self.times = list(self.times)
        if not self.times:
            raise ValueError(f"Medication '{self.name}' needs at least one time")
        for t in self.times:
            _validate_hhmm(t, "Medication time")

    def to_tasks(self, pet_name: str) -> list[Task]:
        """Create one HIGH-priority MEDICATION task per time in `times`."""
        return [
            Task(
                f"{self.name} ({self.dose})",
                t,
                self.start_date,
                TaskType.MEDICATION,
                frequency=self.frequency,
                priority=Priority.HIGH,
                duration_minutes=_MEDICATION_MINUTES,
                pet_name=pet_name,
            )
            for t in self.times
        ]


@dataclass
class SymptomEntry:
    """A symptom the owner noticed on a given day."""

    logged_on: date
    description: str
    severity: Severity


@dataclass
class HealthProfile:
    """A pet's conditions, allergies, medications, symptoms, and readings."""

    conditions: list[str] = field(default_factory=list)
    allergies: list[str] = field(default_factory=list)
    medications: list[Medication] = field(default_factory=list)
    symptoms: list[SymptomEntry] = field(default_factory=list)
    readings: list[HealthReading] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Keep private copies of every list passed in."""
        self.conditions = list(self.conditions)
        self.allergies = list(self.allergies)
        self.medications = list(self.medications)
        self.symptoms = list(self.symptoms)
        self.readings = list(self.readings)

    def add_reading(self, reading: HealthReading) -> None:
        """Store a new health reading."""
        self.readings.append(reading)

    def add_medication(self, med: Medication) -> None:
        """Start tracking a medication (use Pet.add_medication to also schedule reminders)."""
        self.medications.append(med)

    def log_symptom(self, entry: SymptomEntry) -> None:
        """Record a symptom entry."""
        self.symptoms.append(entry)

    def latest_reading(self) -> Optional[HealthReading]:
        """Return the most recent reading, or None if there are none."""
        # reversed() so that on a timestamp tie the last one added wins.
        return max(reversed(self.readings), key=lambda r: r.timestamp, default=None)

    def daily_summary(self, day: date) -> dict:
        """Summarize the readings taken on the given day."""
        todays = sorted(
            (r for r in self.readings if r.timestamp.date() == day),
            key=lambda r: r.timestamp,
        )
        latest = todays[-1] if todays else None

        def average(field_name: str) -> Optional[float]:
            """Mean of one field across today's readings, rounded, or None."""
            if not todays:
                return None
            return round(sum(getattr(r, field_name) for r in todays) / len(todays), 1)

        # Steps, distance, and calories are running totals for the day, so the
        # day's total is the latest reading's value. Summing them would double count.
        return {
            "readings": len(todays),
            "avg_heart_rate": average("heart_rate_bpm"),
            "avg_spo2": average("spo2_percent"),
            "avg_temperature": average("temperature_c"),
            "avg_respiratory_rate": average("respiratory_rate"),
            "total_steps": latest.steps if latest else 0,
            "total_distance_km": latest.distance_km if latest else 0.0,
            "total_calories": latest.calories_burned if latest else 0,
            "latest_sleep_score": latest.sleep_score if latest else None,
            "symptoms": sum(1 for s in self.symptoms if s.logged_on == day),
        }

    def check_alerts(self, species: str) -> list[str]:
        """Return readable alerts for vitals outside the species' normal range."""
        species = species.lower()
        ranges = VITAL_RANGES.get(species)
        reading = self.latest_reading()
        if ranges is None or reading is None:
            return []

        alerts = []
        for field_name, (low, high) in ranges.items():
            value = getattr(reading, field_name)
            label, unit = _VITAL_LABELS[field_name]
            normal = f"{low:g}{unit} or higher" if high is None else f"{low:g} to {high:g}{unit}"
            if value < low:
                direction = "below"
            elif high is not None and value > high:
                direction = "above"
            else:
                continue
            alerts.append(
                f"{label} {value:g}{unit} is {direction} the normal {species} range ({normal})."
            )
        return alerts


class SmartCollar:
    """A simulated collar that produces repeatable vitals from a seed."""

    def __init__(
        self,
        device_id: str,
        seed: int,
        species: str = "dog",
        battery_percent: int = 100,
        is_paired: bool = False,
    ) -> None:
        """Create a collar for one species with a device id and a random seed."""
        self.device_id: str = device_id
        self.seed: int = seed
        self.species: str = species.lower()
        self.battery_percent: int = battery_percent
        self.is_paired: bool = is_paired
        # One generator for the collar's lifetime: a run of readings is repeatable
        # from the seed, but each reading differs. Restarts from the seed after a load.
        self._rng: random.Random = random.Random(seed)
        # Running activity totals for the current day (reset when the date changes).
        self._steps_day: Optional[date] = None
        self._steps: int = 0
        self._last_at: Optional[datetime] = None

    def _centred(self, field_name: str) -> float:
        """Draw a value centred in this collar's species range for one vital."""
        ranges = VITAL_RANGES.get(self.species, VITAL_RANGES[_FALLBACK_SPECIES])
        low, high = ranges[field_name]
        assert high is not None, "only closed ranges are centred (SpO2 is drawn separately)"
        # Mean at the middle, 4 standard deviations to each edge: almost always normal.
        return self._rng.gauss((low + high) / 2, (high - low) / 8)

    def _advance_steps(self, at: datetime, rate: float) -> int:
        """Add steps for the minutes since the last reading today; return the day's total."""
        if at.date() != self._steps_day or self._last_at is None:
            self._steps_day = at.date()
            self._steps = 0
            self._last_at = datetime.combine(at.date(), datetime.min.time(), tzinfo=at.tzinfo)
        # A reading earlier than the last one adds nothing (totals never go down).
        minutes = max(0.0, (at - self._last_at).total_seconds() / 60)
        self._steps += round(minutes * rate)
        self._last_at = max(self._last_at, at)
        return self._steps

    def read_vitals(self, at: datetime) -> HealthReading:
        """Generate a plausible health reading timestamped `at`, repeatable from the seed."""
        # Always draw in the same order so the sequence stays repeatable from the seed.
        heart_rate = round(self._centred("heart_rate_bpm"))
        temperature = round(self._centred("temperature_c"), 1)
        respiratory = round(self._centred("respiratory_rate"))
        spo2 = round(self._rng.uniform(95.5, 99.5), 1)
        sleep = min(100, max(0, self._rng.randint(60, 95)))
        rate = self._rng.uniform(*_STEP_RATE)

        steps = self._advance_steps(at, rate)
        self.battery_percent = max(0, self.battery_percent - 1)
        return HealthReading(
            timestamp=at,
            heart_rate_bpm=max(1, heart_rate),
            spo2_percent=spo2,
            temperature_c=temperature,
            respiratory_rate=max(1, respiratory),
            sleep_score=sleep,
            steps=steps,
            distance_km=round(steps * _KM_PER_STEP, 2),
            calories_burned=round(steps * _KCAL_PER_STEP),
        )


# ---------------------------------------------------------------------------
# Core Scheduling
# ---------------------------------------------------------------------------

@dataclass(eq=False)
class Task:
    """A single care task for a pet at a given date and time."""

    description: str
    time: str
    due_date: date
    task_type: TaskType
    frequency: Frequency = Frequency.ONCE
    priority: Priority = Priority.MEDIUM
    duration_minutes: int = 15
    completed: bool = False
    pet_name: str = ""

    def __post_init__(self) -> None:
        """Validate that time is a zero-padded 24-hour "HH:MM" string."""
        _validate_hhmm(self.time, "time")

    def mark_complete(self) -> Optional[Task]:
        """Mark this task done and return its next occurrence, if any."""
        self.completed = True
        return self.next_occurrence()

    def next_occurrence(self) -> Optional[Task]:
        """Return the next copy of a recurring task, or None for a one-time task."""
        step = _RECURRENCE_STEP.get(self.frequency)
        if step is None:
            return None
        return replace(self, due_date=self.due_date + step, completed=False)


@dataclass(eq=False)
class Pet:
    """A pet with its care tasks, health profile, and optional collar."""

    name: str
    species: str
    breed: str
    age_years: float
    weight_kg: float
    tasks: list[Task] = field(default_factory=list)
    health: HealthProfile = field(default_factory=HealthProfile)
    collar: Optional[SmartCollar] = None

    def __post_init__(self) -> None:
        """Store species lowercase and keep a private copy of the task list."""
        self.species = self.species.lower()
        self.tasks = list(self.tasks)

    def _find_task(self, description: str, time: str) -> Optional[Task]:
        """Return the earliest-due incomplete task matching description and time."""
        matches = [
            t for t in self.tasks
            if t.description == description and t.time == time and not t.completed
        ]
        return min(matches, key=lambda t: t.due_date, default=None)

    def _is_duplicate(self, task: Task, ignore: Optional[Task] = None) -> bool:
        """Return True if another task has the same description, time, and due_date."""
        return any(
            other is not ignore
            and other.description == task.description
            and other.time == task.time
            and other.due_date == task.due_date
            for other in self.tasks
        )

    def add_task(self, task: Task) -> None:
        """Add a task to this pet and set its pet_name."""
        if self._is_duplicate(task):
            raise ValueError(
                f"{self.name} already has '{task.description}' at {task.time} on {task.due_date}"
            )
        task.pet_name = self.name
        self.tasks.append(task)

    def remove_task(self, description: str, time: str) -> bool:
        """Remove the earliest-due incomplete matching task; return True if removed."""
        task = self._find_task(description, time)
        if task is None:
            return False
        self.tasks.remove(task)
        return True

    def update_task(self, description: str, time: str, changes: dict) -> bool:
        """Replace the earliest-due incomplete match with an edited copy; return False if none."""
        task = self._find_task(description, time)
        if task is None:
            return False
        try:
            edited = replace(task, **changes)  # re-runs __post_init__ validation
        except TypeError as exc:
            raise ValueError(f"Unknown task field in changes: {exc}") from exc
        edited.pet_name = self.name
        if self._is_duplicate(edited, ignore=task):
            raise ValueError(
                f"{self.name} already has '{edited.description}' at {edited.time} "
                f"on {edited.due_date}"
            )
        self.tasks[self.tasks.index(task)] = edited
        return True

    def get_tasks(self) -> list[Task]:
        """Return this pet's tasks."""
        return list(self.tasks)

    def add_medication(self, med: Medication) -> None:
        """Track a medication and add its reminder tasks to this pet."""
        tasks = med.to_tasks(self.name)
        # Check every dose before changing anything, so a duplicate second dose
        # can't leave the first dose scheduled without its medication.
        for i, task in enumerate(tasks):
            clashes_with_new = any(
                other.time == task.time and other.due_date == task.due_date
                for other in tasks[:i]
            )
            if clashes_with_new or self._is_duplicate(task):
                raise ValueError(
                    f"{self.name} already has '{task.description}' at {task.time} "
                    f"on {task.due_date}"
                )
        self.health.add_medication(med)
        for task in tasks:
            self.add_task(task)

    def pair_collar(self, collar: SmartCollar) -> None:
        """Pair a smart collar with this pet."""
        if self.collar is not None:
            raise ValueError(f"{self.name} already has a collar ({self.collar.device_id})")
        if collar.is_paired:
            raise ValueError(f"Collar {collar.device_id} is already paired")
        if collar.species != self.species:
            raise ValueError(
                f"Collar {collar.device_id} is for a {collar.species}, "
                f"but {self.name} is a {self.species}"
            )
        collar.is_paired = True
        self.collar = collar

    def sync_collar(self, at: datetime) -> Optional[HealthReading]:
        """Read vitals from the paired collar, or return None if no collar is paired."""
        if self.collar is None:
            return None
        reading = self.collar.read_vitals(at)
        self.health.add_reading(reading)
        return reading


class Owner:
    """A pet owner with their pets, daily constraints, cart, and orders."""

    def __init__(
        self,
        name: str,
        email: str = "",
        address: str = "",
        available_minutes: int = 120,
        day_start: str = "07:00",
        day_end: str = "21:00",
        preferred_types: Optional[list[TaskType]] = None,
    ) -> None:
        """Create an owner with contact info and scheduling preferences."""
        _validate_hhmm(day_start, "day_start")
        _validate_hhmm(day_end, "day_end")
        if _to_minutes(day_start) >= _to_minutes(day_end):
            raise ValueError(
                f"day_start must be before day_end (overnight windows are not supported), "
                f"got {day_start} to {day_end}"
            )
        if available_minutes < 0:
            raise ValueError(f"available_minutes cannot be negative, got {available_minutes}")
        self.name: str = name
        self.email: str = email
        self.address: str = address
        self.available_minutes: int = available_minutes
        self.day_start: str = day_start
        self.day_end: str = day_end
        self.preferred_types: list[TaskType] = list(preferred_types or [])
        self.pets: list[Pet] = []
        self.cart: Cart = Cart()
        self.orders: list[Order] = []

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        if self.get_pet(pet.name) is not None:
            raise ValueError(f"A pet named '{pet.name}' already exists")
        self.pets.append(pet)

    def remove_pet(self, name: str) -> bool:
        """Remove a pet by name; return True if one was removed."""
        pet = self.get_pet(name)
        if pet is None:
            return False
        self.pets.remove(pet)
        return True

    def get_pet(self, name: str) -> Optional[Pet]:
        """Return the pet with this name, or None if not found."""
        wanted = name.lower()
        return next((p for p in self.pets if p.name.lower() == wanted), None)

    def get_all_tasks(self) -> list[Task]:
        """Return every task across all of this owner's pets."""
        return [task for pet in self.pets for task in pet.get_tasks()]

    def save_to_json(self, path: str) -> None:
        """Save this owner and all their data to a JSON file."""
        raise NotImplementedError

    @classmethod
    def load_from_json(cls, path: str) -> Owner:
        """Load an owner and all their data from a JSON file."""
        raise NotImplementedError


class Scheduler:
    """Plans, sorts, filters, and completes tasks using the owner's task list."""

    def __init__(self, owner: Owner) -> None:
        """Create a scheduler for one owner."""
        self.owner: Owner = owner

    def get_todays_schedule(self, day: date) -> list[Task]:
        """Return all tasks due on the given day, sorted by time."""
        todays = [t for t in self.owner.get_all_tasks() if t.due_date == day]
        return sorted(todays, key=lambda t: t.time)

    def _rank_key(self, task: Task) -> tuple[int, int, str]:
        """Rank by priority (HIGH first), then preferred-type position, then time."""
        prefs = self.owner.preferred_types
        pref_rank = prefs.index(task.task_type) if task.task_type in prefs else len(prefs)
        return (_PRIORITY_RANK[task.priority], pref_rank, task.time)

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Return the tasks sorted by their HH:MM time."""
        # Zero-padded "HH:MM" (enforced by _validate_hhmm) sorts correctly as text.
        return sorted(tasks, key=lambda t: t.time)

    def sort_by_priority(self, tasks: list[Task]) -> list[Task]:
        """Return the tasks sorted with HIGH priority first."""
        return sorted(tasks, key=self._rank_key)

    def filter_tasks(
        self, pet_name: Optional[str] = None, completed: Optional[bool] = None
    ) -> list[Task]:
        """Return tasks matching the given pet and completion status; None skips that filter."""
        return [
            t for t in self.owner.get_all_tasks()
            if (pet_name is None or t.pet_name.lower() == pet_name.lower())
            and (completed is None or t.completed == completed)
        ]

    def detect_conflicts(self, day: date) -> list[str]:
        """Return a warning for each pair of incomplete tasks sharing the same date and time."""
        # Exact date + time match only (documented tradeoff: overlaps are not checked).
        # Completed tasks are done, so they can't clash with anything still to do.
        by_time: dict[str, list[Task]] = {}
        for task in self.get_todays_schedule(day):
            if not task.completed:
                by_time.setdefault(task.time, []).append(task)

        return [
            f"Conflict on {day} at {time}: {a.pet_name}'s '{a.description}' "
            f"and {b.pet_name}'s '{b.description}'"
            for time, tasks in by_time.items()
            for a, b in combinations(tasks, 2)
        ]

    def mark_task_complete(self, pet_name: str, description: str, time: str) -> Optional[Task]:
        """Complete the earliest-due incomplete match and return its next occurrence, if any."""
        pet = self.owner.get_pet(pet_name)
        if pet is None:
            return None
        # Tasks come only from owner.get_all_tasks(); pet.name is the canonical spelling
        # that add_task() stamped on each task, so this match is exact.
        pet_tasks = [t for t in self.owner.get_all_tasks() if t.pet_name == pet.name]
        matches = [
            t for t in pet_tasks
            if t.description == description and t.time == time and not t.completed
        ]
        task = min(matches, key=lambda t: t.due_date, default=None)
        if task is None:
            return None
        upcoming = task.mark_complete()
        if upcoming is None:
            return None
        # Same check as Pet._is_duplicate: if the next occurrence is already there
        # (completed or not), hand it back instead of adding a copy.
        existing = next(
            (t for t in pet_tasks
             if t.description == upcoming.description
             and t.time == upcoming.time
             and t.due_date == upcoming.due_date),
            None,
        )
        if existing is not None:
            return existing
        pet.add_task(upcoming)
        return upcoming

    def _hours_problem(self, task: Task) -> Optional[str]:
        """Return why a task falls outside the owner's hours, or None if it fits."""
        start = _to_minutes(task.time)
        end = start + task.duration_minutes
        day_start, day_end = _to_minutes(self.owner.day_start), _to_minutes(self.owner.day_end)
        if start < day_start or start >= day_end:
            return f"Outside your hours ({self.owner.day_start} to {self.owner.day_end})."
        if end > day_end:
            return f"Would run past your hours (ends {_from_minutes(end)})."
        return None

    @staticmethod
    def _medication_reason(outside_hours: bool, over_budget: bool) -> str:
        """Explain a kept medication, naming any owner constraint the rule overrode."""
        if outside_hours and over_budget:
            overrode = "it's outside your hours and goes over your available time"
        elif outside_hours:
            overrode = "it's outside your hours"
        elif over_budget:
            overrode = "it goes over your available time"
        else:
            return "Medication, always kept (health first)."
        return f"Medication, kept even though {overrode} (health first)."

    def _why_chosen(self, task: Task) -> str:
        """Explain a planned non-medication task: its priority and any preferred type."""
        reason = f"{task.priority.value.capitalize()} priority"
        if task.task_type in self.owner.preferred_types:
            reason += f", you prefer {_TYPE_LABELS[task.task_type]}"
        return reason + "."

    def _plan(self, day: date) -> tuple[list[Task], list[Task], dict[Task, str]]:
        """Decide the day's plan once; return (chosen, skipped, reason for each task)."""
        todays = [t for t in self.get_todays_schedule(day) if not t.completed]  # rule 1
        chosen: list[Task] = []
        skipped: list[Task] = []
        candidates: list[Task] = []
        reasons: dict[Task, str] = {}  # keyed by identity: Task uses eq=False
        minutes_left = self.owner.available_minutes

        for task in todays:
            hours_problem = self._hours_problem(task)
            if task.task_type is TaskType.MEDICATION:  # rule 2: health first, minutes still count
                minutes_left -= task.duration_minutes
                chosen.append(task)
                reasons[task] = self._medication_reason(hours_problem is not None, minutes_left < 0)
            elif hours_problem is not None:  # rule 3
                skipped.append(task)
                reasons[task] = hours_problem
            else:
                candidates.append(task)

        for task in sorted(candidates, key=self._rank_key):  # rule 4
            if task.duration_minutes <= minutes_left:  # rule 5: take it if it fits...
                chosen.append(task)
                minutes_left -= task.duration_minutes
                reasons[task] = self._why_chosen(task)
            else:  # ...otherwise skip it and keep trying smaller tasks
                skipped.append(task)
                reasons[task] = (
                    f"Not enough time left (needs {task.duration_minutes} min, "
                    f"{max(minutes_left, 0)} min left)."
                )

        return self.sort_by_time(chosen), self.sort_by_time(skipped), reasons  # rule 6

    def build_daily_plan(self, day: date) -> list[Task]:
        """Choose the day's tasks that fit the owner's time and hours, sorted by time."""
        chosen, _, _ = self._plan(day)
        return chosen

    def skipped_tasks(self, day: date) -> list[Task]:
        """Return the day's tasks that did not make the plan."""
        _, skipped, _ = self._plan(day)
        return skipped

    def explain_plan(self, day: date) -> list[str]:
        """Return one plain-English reason for each chosen or skipped task."""
        chosen, skipped, reasons = self._plan(day)
        planned = set(chosen)
        return [
            f"{t.time} {t.description} ({t.pet_name}, {t.duration_minutes} min): "
            f"{'planned' if t in planned else 'skipped'}. {reasons[t]}"
            for t in self.sort_by_time(chosen + skipped)
        ]


# ---------------------------------------------------------------------------
# Food Marketplace
# ---------------------------------------------------------------------------

@dataclass
class FoodProduct:
    """A food product in the simulated store."""

    product_id: str
    brand: str
    name: str
    species: str
    life_stage: str
    price: float
    rating: float
    kcal_per_cup: int
    supports: list[str] = field(default_factory=list)
    allergens: list[str] = field(default_factory=list)


@dataclass
class CartItem:
    """A product and how many of it are in the cart."""

    product: FoodProduct
    quantity: int = 1

    def subtotal(self) -> float:
        """Return price times quantity."""
        raise NotImplementedError


@dataclass(kw_only=True)
class Order:
    """A placed order with its items, total, status, and delivery details."""

    order_id: str
    items: list[CartItem] = field(default_factory=list)
    total: float
    status: OrderStatus = OrderStatus.PLACED
    placed_on: date
    delivery_date: date
    delivery_address: str

    def advance_status(self) -> bool:
        """Move PLACED to SHIPPED to DELIVERED; return False if it cannot advance."""
        raise NotImplementedError

    def to_delivery_task(self, pet_name: str) -> Task:
        """Create a DELIVERY task on the delivery date."""
        raise NotImplementedError


class MockPayment:
    """A fake payment processor that never handles card details."""

    def charge(self, amount: float) -> bool:
        """Return True if the amount is greater than zero."""
        raise NotImplementedError


class Cart:
    """An owner's shopping cart."""

    def __init__(self) -> None:
        """Create an empty cart."""
        self.items: list[CartItem] = []

    def add_item(self, product: FoodProduct, quantity: int) -> None:
        """Add a product to the cart."""
        raise NotImplementedError

    def remove_item(self, product_id: str) -> bool:
        """Remove a product from the cart; return True if it was there."""
        raise NotImplementedError

    def total(self) -> float:
        """Return the sum of all item subtotals."""
        raise NotImplementedError

    def clear(self) -> None:
        """Empty the cart."""
        raise NotImplementedError

    def checkout(
        self, owner: Owner, payment: MockPayment, pet_name: str, today: date
    ) -> Order:
        """Charge, create an Order with a delivery task for the pet, and clear the cart."""
        raise NotImplementedError


class Marketplace:
    """Searches, scores, recommends, and compares food products."""

    def __init__(self, catalog: Optional[list[FoodProduct]] = None) -> None:
        """Create a marketplace with a product catalog."""
        self.catalog: list[FoodProduct] = catalog if catalog is not None else []

    def search(self, species: str, query: str) -> list[FoodProduct]:
        """Return products for a species whose name or brand matches the query."""
        raise NotImplementedError

    def score(self, product: FoodProduct, pet: Pet) -> float:
        """Return how well a product fits a pet."""
        raise NotImplementedError

    def recommend_for(self, pet: Pet, top_n: int) -> list[FoodProduct]:
        """Return the top-scoring safe products for a pet."""
        raise NotImplementedError

    def explain_recommendation(self, product: FoodProduct, pet: Pet) -> list[str]:
        """Return the exact factors score() used for this product and pet."""
        raise NotImplementedError

    def compare(self, product_ids: list[str]) -> list[dict]:
        """Return a side-by-side comparison of the given products."""
        raise NotImplementedError
