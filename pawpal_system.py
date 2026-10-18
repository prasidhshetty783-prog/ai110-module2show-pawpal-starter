"""PawPal+ logic layer: owners, pets, tasks, scheduling, health tracking, and a food marketplace.

Built from diagrams/uml.mmd. Core scheduling, the health tracker, the food
marketplace, and JSON save and load are implemented.
"""

from __future__ import annotations

import json
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
        # Build the full text first: if anything can't be serialized, the old
        # file is left untouched instead of being truncated halfway through.
        text = json.dumps(_owner_to_dict(self), indent=2)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    @classmethod
    def load_from_json(cls, path: str) -> Owner:
        """Load an owner and all their data from a JSON file."""
        with open(path, encoding="utf-8") as f:
            return _owner_from_dict(json.load(f))


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

    def skip_reasons(self, day: date) -> dict[Task, str]:
        """Return each skipped task of the day mapped to why it did not make the plan."""
        _, skipped, reasons = self._plan(day)
        return {t: reasons[t] for t in skipped}

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

# Life stages a product can target. A pet's own stage is never "all".
_LIFE_STAGES = ("young", "adult", "senior", "all")

# Recommendation score weights. Health comes first: one matching condition (3)
# outweighs a life-stage match (2) or a perfect rating (2) on its own.
_CONDITION_POINTS = 3.0  # per pet condition the product supports
_LIFE_STAGE_POINTS = 2.0  # product made for the pet's stage, or for "all"
_RATING_POINTS = 2.0  # scaled by rating / 5
_PRICE_POINTS = 1.0  # scaled by how far below _PRICE_CEILING the price is
_PRICE_CEILING = 100.0  # every SAMPLE_CATALOG price stays below this

# Every food order is delivered this many days after it is placed.
_DELIVERY_DAYS = 3
_DELIVERY_TIME = "12:00"
_DELIVERY_MINUTES = 10


def _life_stage(age_years: float) -> str:
    """Return "young" under 1 year, "adult" from 1 to under 7, and "senior" from 7."""
    if age_years < 1:
        return "young"
    if age_years < 7:
        return "adult"
    return "senior"


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

    def __post_init__(self) -> None:
        """Store species lowercase, check the life stage, and copy the lists."""
        self.species = self.species.lower()
        if self.life_stage not in _LIFE_STAGES:
            raise ValueError(
                f"life_stage must be one of {', '.join(_LIFE_STAGES)}, got {self.life_stage!r}"
            )
        self.supports = list(self.supports)
        self.allergens = list(self.allergens)


# Fictional brands only. Every price is below _PRICE_CEILING (tested).
SAMPLE_CATALOG: list[FoodProduct] = [
    FoodProduct("D01", "Barkley Farms", "Lamb & Rice Adult", "dog", "adult", 42.99, 4.5, 380,
                supports=["sensitive skin", "digestion"]),
    FoodProduct("D02", "Barkley Farms", "Chicken Feast Puppy", "dog", "young", 38.50, 4.3, 410,
                supports=["digestion"], allergens=["chicken"]),
    FoodProduct("D03", "Tailwind Kitchen", "Golden Years Joint Care", "dog", "senior",
                54.00, 4.7, 340, supports=["joint health", "weight control"],
                allergens=["chicken"]),
    FoodProduct("D04", "Tailwind Kitchen", "Salmon Skin & Coat", "dog", "all", 61.25, 4.6, 360,
                supports=["sensitive skin"], allergens=["fish"]),
    FoodProduct("D05", "Muttley & Co.", "Beef Hearty Bites", "dog", "adult", 29.99, 4.0, 400,
                allergens=["beef", "grain"]),
    FoodProduct("D06", "Muttley & Co.", "Lite Turkey Formula", "dog", "adult", 34.75, 4.1, 320,
                supports=["weight control"]),
    FoodProduct("D07", "Fernhollow", "Senior Gentle Duck", "dog", "senior", 47.50, 4.4, 330,
                supports=["joint health", "digestion"]),
    FoodProduct("C01", "Purrfect Bowl", "Ocean Whitefish Adult", "cat", "adult", 32.99, 4.4, 390,
                supports=["urinary health"], allergens=["fish"]),
    FoodProduct("C02", "Purrfect Bowl", "Kitten Chicken Starter", "cat", "young", 27.50, 4.6, 420,
                supports=["digestion"], allergens=["chicken"]),
    FoodProduct("C03", "Whiskerwell", "Urinary Care Turkey", "cat", "adult", 44.00, 4.5, 350,
                supports=["urinary health"]),
    FoodProduct("C04", "Whiskerwell", "Senior Vitality Tuna", "cat", "senior", 39.99, 4.2, 340,
                supports=["joint health", "weight control"], allergens=["fish"]),
    FoodProduct("C05", "Nibble Lane", "Indoor Rabbit Recipe", "cat", "all", 49.95, 4.8, 370,
                supports=["weight control", "sensitive skin"]),
]


@dataclass
class CartItem:
    """A product and how many of it are in the cart."""

    product: FoodProduct
    quantity: int = 1

    def subtotal(self) -> float:
        """Return price times quantity."""
        return round(self.product.price * self.quantity, 2)


# Each status and the one that follows it. DELIVERED has no next status.
_NEXT_STATUS: dict[OrderStatus, OrderStatus] = {
    OrderStatus.PLACED: OrderStatus.SHIPPED,
    OrderStatus.SHIPPED: OrderStatus.DELIVERED,
}


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
        next_status = _NEXT_STATUS.get(self.status)
        if next_status is None:
            return False
        self.status = next_status
        return True

    def to_delivery_task(self, pet_name: str) -> Task:
        """Create a DELIVERY task on the delivery date."""
        return Task(
            f"Food delivery ({self.order_id})",
            _DELIVERY_TIME,
            self.delivery_date,
            TaskType.DELIVERY,
            frequency=Frequency.ONCE,
            priority=Priority.MEDIUM,
            duration_minutes=_DELIVERY_MINUTES,
            pet_name=pet_name,
        )


class MockPayment:
    """A fake payment processor that never handles card details."""

    def charge(self, amount: float) -> bool:
        """Return True if the amount is greater than zero."""
        # Simulated only: no card number, CVV, or any other payment detail is
        # requested, accepted, or stored anywhere.
        return amount > 0


class Cart:
    """An owner's shopping cart."""

    def __init__(self) -> None:
        """Create an empty cart."""
        self.items: list[CartItem] = []

    def add_item(self, product: FoodProduct, quantity: int) -> None:
        """Add a product to the cart, or raise its quantity if it is already there."""
        if quantity < 1:
            raise ValueError(f"quantity must be at least 1, got {quantity}")
        for item in self.items:
            if item.product.product_id == product.product_id:
                item.quantity += quantity
                return
        self.items.append(CartItem(product, quantity))

    def remove_item(self, product_id: str) -> bool:
        """Remove a product from the cart; return True if it was there."""
        for item in self.items:
            if item.product.product_id == product_id:
                self.items.remove(item)
                return True
        return False

    def total(self) -> float:
        """Return the sum of all item subtotals."""
        return round(sum(item.subtotal() for item in self.items), 2)

    def clear(self) -> None:
        """Empty the cart."""
        self.items.clear()

    def checkout(
        self, owner: Owner, payment: MockPayment, pet_name: str, today: date
    ) -> Order:
        """Charge, create an Order with a delivery task for the pet, and clear the cart."""
        # Every check runs before anything changes, so a failed checkout leaves
        # the cart, the owner's orders, and the pet's tasks exactly as they were.
        if not self.items:
            raise ValueError("Cannot check out an empty cart")
        pet = owner.get_pet(pet_name)
        if pet is None:
            raise ValueError(f"No pet named '{pet_name}'")
        total = self.total()
        if not payment.charge(total):
            raise ValueError(f"Payment of ${total:.2f} was declined")

        order = Order(
            # Orders are never deleted, so the count gives a unique, increasing ID.
            order_id=f"ORD-{len(owner.orders) + 1:04d}",
            items=list(self.items),  # a copy: clear() below must not empty the order
            total=total,
            placed_on=today,
            delivery_date=today + timedelta(days=_DELIVERY_DAYS),
            delivery_address=owner.address,
        )
        pet.add_task(order.to_delivery_task(pet.name))
        owner.orders.append(order)
        self.clear()
        return order


class Marketplace:
    """Searches, scores, recommends, and compares food products."""

    def __init__(self, catalog: Optional[list[FoodProduct]] = None) -> None:
        """Create a marketplace with a product catalog."""
        self.catalog: list[FoodProduct] = list(catalog or [])

    def search(self, species: str, query: str) -> list[FoodProduct]:
        """Return products for a species whose name or brand matches the query."""
        species, query = species.lower(), query.lower()
        return [
            p for p in self.catalog
            if p.species == species
            and (query in p.name.lower() or query in p.brand.lower())
        ]

    def _exclusion_reason(self, product: FoodProduct, pet: Pet) -> Optional[str]:
        """Return why a product is unsafe for a pet (wrong species or allergen), or None."""
        if product.species != pet.species:
            return f"Excluded: made for {product.species}s, but {pet.name} is a {pet.species}."
        allergies = {a.lower() for a in pet.health.allergies}
        for allergen in product.allergens:
            if allergen.lower() in allergies:
                return f"Excluded: contains {allergen}, and {pet.name} is allergic to it."
        return None

    def _score_factors(self, product: FoodProduct, pet: Pet) -> list[tuple[str, float]]:
        """Return (reason, points) for every factor in a safe product's score."""
        # The single source of truth: score() sums these points and
        # explain_recommendation() prints them, so the two can never disagree.
        # Points are rounded here so the printed points add up to the score exactly.
        factors: list[tuple[str, float]] = []

        supports = {s.lower() for s in product.supports}
        # dict.fromkeys drops repeated conditions but keeps the pet's order.
        for condition in dict.fromkeys(c.lower() for c in pet.health.conditions):
            if condition in supports:
                factors.append((f"Supports {condition}, one of {pet.name}'s conditions",
                                _CONDITION_POINTS))

        stage = _life_stage(pet.age_years)
        if product.life_stage == stage:
            factors.append((f"Made for {stage} pets, and {pet.name} is {stage}",
                            _LIFE_STAGE_POINTS))
        elif product.life_stage == "all":
            factors.append(("Suitable for all life stages", _LIFE_STAGE_POINTS))

        factors.append((f"Rated {product.rating:g}/5",
                         round(_RATING_POINTS * product.rating / 5, 2)))
        price_share = max(0.0, 1 - product.price / _PRICE_CEILING)
        factors.append((f"Price ${product.price:.2f}", round(_PRICE_POINTS * price_share, 2)))
        return factors

    def score(self, product: FoodProduct, pet: Pet) -> float:
        """Return how well a product fits a pet (0.0 if it is unsafe for the pet)."""
        if self._exclusion_reason(product, pet) is not None:
            return 0.0
        return round(sum(points for _, points in self._score_factors(product, pet)), 2)

    def recommend_for(self, pet: Pet, top_n: int) -> list[FoodProduct]:
        """Return the top-scoring safe products for a pet."""
        safe = [p for p in self.catalog if self._exclusion_reason(p, pet) is None]
        # Ties go to the cheaper product, then the product id, so results are stable.
        ranked = sorted(safe, key=lambda p: (-self.score(p, pet), p.price, p.product_id))
        return ranked[:max(top_n, 0)]

    def explain_recommendation(self, product: FoodProduct, pet: Pet) -> list[str]:
        """Return the exact factors score() used for this product and pet."""
        reason = self._exclusion_reason(product, pet)
        if reason is not None:
            return [reason]
        return [f"{text} ({points:+.2f})" for text, points in self._score_factors(product, pet)]

    def compare(self, product_ids: list[str]) -> list[dict]:
        """Return a side-by-side comparison of the given products."""
        by_id = {p.product_id: p for p in self.catalog}
        return [
            {
                "product_id": p.product_id,
                "brand": p.brand,
                "name": p.name,
                "species": p.species,
                "life_stage": p.life_stage,
                "price": p.price,
                "rating": p.rating,
                "kcal_per_cup": p.kcal_per_cup,
                "supports": list(p.supports),
                "allergens": list(p.allergens),
            }
            for p in (by_id[pid] for pid in product_ids if pid in by_id)
        ]


# ---------------------------------------------------------------------------
# Save and load (private helpers for Owner.save_to_json / Owner.load_from_json)
# ---------------------------------------------------------------------------
# Enums are stored as their values and dates/datetimes as ISO strings, so the
# file is plain JSON. Every _from_dict rebuilds through the normal constructors,
# so a hand-edited file goes through the same validation as user input.

def _task_to_dict(task: Task) -> dict:
    """Turn a Task into JSON-ready data (pet_name comes from the pet it is nested under)."""
    return {
        "description": task.description,
        "time": task.time,
        "due_date": task.due_date.isoformat(),
        "task_type": task.task_type.value,
        "frequency": task.frequency.value,
        "priority": task.priority.value,
        "duration_minutes": task.duration_minutes,
        "completed": task.completed,
    }


def _task_from_dict(data: dict) -> Task:
    """Rebuild a Task; Pet.add_task() sets its pet_name."""
    return Task(
        data["description"],
        data["time"],
        date.fromisoformat(data["due_date"]),
        TaskType(data["task_type"]),
        frequency=Frequency(data["frequency"]),
        priority=Priority(data["priority"]),
        duration_minutes=data["duration_minutes"],
        completed=data["completed"],
    )


def _medication_to_dict(med: Medication) -> dict:
    """Turn a Medication into JSON-ready data."""
    return {
        "name": med.name,
        "dose": med.dose,
        "times": list(med.times),
        "frequency": med.frequency.value,
        "start_date": med.start_date.isoformat(),
    }


def _medication_from_dict(data: dict) -> Medication:
    """Rebuild a Medication (its reminder tasks are restored separately, as tasks)."""
    return Medication(
        name=data["name"],
        dose=data["dose"],
        times=data["times"],
        frequency=Frequency(data["frequency"]),
        start_date=date.fromisoformat(data["start_date"]),
    )


def _symptom_to_dict(entry: SymptomEntry) -> dict:
    """Turn a SymptomEntry into JSON-ready data."""
    return {
        "logged_on": entry.logged_on.isoformat(),
        "description": entry.description,
        "severity": entry.severity.value,
    }


def _symptom_from_dict(data: dict) -> SymptomEntry:
    """Rebuild a SymptomEntry."""
    return SymptomEntry(
        logged_on=date.fromisoformat(data["logged_on"]),
        description=data["description"],
        severity=Severity(data["severity"]),
    )


def _reading_to_dict(reading: HealthReading) -> dict:
    """Turn a HealthReading into JSON-ready data."""
    return {
        "timestamp": reading.timestamp.isoformat(),
        "heart_rate_bpm": reading.heart_rate_bpm,
        "spo2_percent": reading.spo2_percent,
        "temperature_c": reading.temperature_c,
        "respiratory_rate": reading.respiratory_rate,
        "sleep_score": reading.sleep_score,
        "steps": reading.steps,
        "distance_km": reading.distance_km,
        "calories_burned": reading.calories_burned,
    }


def _reading_from_dict(data: dict) -> HealthReading:
    """Rebuild a HealthReading."""
    return HealthReading(
        timestamp=datetime.fromisoformat(data["timestamp"]),
        heart_rate_bpm=data["heart_rate_bpm"],
        spo2_percent=data["spo2_percent"],
        temperature_c=data["temperature_c"],
        respiratory_rate=data["respiratory_rate"],
        sleep_score=data["sleep_score"],
        steps=data["steps"],
        distance_km=data["distance_km"],
        calories_burned=data["calories_burned"],
    )


def _health_to_dict(health: HealthProfile) -> dict:
    """Turn a HealthProfile into JSON-ready data."""
    return {
        "conditions": list(health.conditions),
        "allergies": list(health.allergies),
        "medications": [_medication_to_dict(m) for m in health.medications],
        "symptoms": [_symptom_to_dict(s) for s in health.symptoms],
        "readings": [_reading_to_dict(r) for r in health.readings],
    }


def _health_from_dict(data: dict) -> HealthProfile:
    """Rebuild a HealthProfile, restoring medications directly (no duplicate reminder tasks)."""
    return HealthProfile(
        conditions=data["conditions"],
        allergies=data["allergies"],
        medications=[_medication_from_dict(m) for m in data["medications"]],
        symptoms=[_symptom_from_dict(s) for s in data["symptoms"]],
        readings=[_reading_from_dict(r) for r in data["readings"]],
    )


def _collar_to_dict(collar: SmartCollar) -> dict:
    """Turn a SmartCollar's settings into JSON-ready data (its RNG state is not saved)."""
    return {
        "device_id": collar.device_id,
        "seed": collar.seed,
        "species": collar.species,
        "battery_percent": collar.battery_percent,
        "is_paired": collar.is_paired,
    }


def _collar_from_dict(data: dict) -> SmartCollar:
    """Rebuild a SmartCollar; its random generator restarts from the seed."""
    return SmartCollar(
        data["device_id"],
        data["seed"],
        species=data["species"],
        battery_percent=data["battery_percent"],
        is_paired=data["is_paired"],
    )


def _pet_to_dict(pet: Pet) -> dict:
    """Turn a Pet, its tasks, health profile, and collar into JSON-ready data."""
    return {
        "name": pet.name,
        "species": pet.species,
        "breed": pet.breed,
        "age_years": pet.age_years,
        "weight_kg": pet.weight_kg,
        "tasks": [_task_to_dict(t) for t in pet.tasks],
        "health": _health_to_dict(pet.health),
        "collar": None if pet.collar is None else _collar_to_dict(pet.collar),
    }


def _pet_from_dict(data: dict) -> Pet:
    """Rebuild a Pet with its tasks, health profile, and collar."""
    pet = Pet(
        data["name"],
        data["species"],
        data["breed"],
        data["age_years"],
        data["weight_kg"],
        health=_health_from_dict(data["health"]),
    )
    for task_data in data["tasks"]:
        pet.add_task(_task_from_dict(task_data))  # sets pet_name, rejects duplicates
    if data["collar"] is not None:
        # Attached directly: pair_collar() would refuse a collar saved as is_paired=True.
        pet.collar = _collar_from_dict(data["collar"])
    return pet


def _product_to_dict(product: FoodProduct) -> dict:
    """Turn a FoodProduct into JSON-ready data."""
    return {
        "product_id": product.product_id,
        "brand": product.brand,
        "name": product.name,
        "species": product.species,
        "life_stage": product.life_stage,
        "price": product.price,
        "rating": product.rating,
        "kcal_per_cup": product.kcal_per_cup,
        "supports": list(product.supports),
        "allergens": list(product.allergens),
    }


def _product_from_dict(data: dict) -> FoodProduct:
    """Rebuild a FoodProduct."""
    return FoodProduct(
        data["product_id"],
        data["brand"],
        data["name"],
        data["species"],
        data["life_stage"],
        data["price"],
        data["rating"],
        data["kcal_per_cup"],
        supports=data["supports"],
        allergens=data["allergens"],
    )


def _cart_item_to_dict(item: CartItem) -> dict:
    """Turn a CartItem into JSON-ready data."""
    return {"product": _product_to_dict(item.product), "quantity": item.quantity}


def _cart_item_from_dict(data: dict) -> CartItem:
    """Rebuild a CartItem."""
    return CartItem(_product_from_dict(data["product"]), data["quantity"])


def _order_to_dict(order: Order) -> dict:
    """Turn an Order into JSON-ready data."""
    return {
        "order_id": order.order_id,
        "items": [_cart_item_to_dict(i) for i in order.items],
        "total": order.total,
        "status": order.status.value,
        "placed_on": order.placed_on.isoformat(),
        "delivery_date": order.delivery_date.isoformat(),
        "delivery_address": order.delivery_address,
    }


def _order_from_dict(data: dict) -> Order:
    """Rebuild an Order."""
    return Order(
        order_id=data["order_id"],
        items=[_cart_item_from_dict(i) for i in data["items"]],
        total=data["total"],
        status=OrderStatus(data["status"]),
        placed_on=date.fromisoformat(data["placed_on"]),
        delivery_date=date.fromisoformat(data["delivery_date"]),
        delivery_address=data["delivery_address"],
    )


def _owner_to_dict(owner: Owner) -> dict:
    """Turn an Owner and everything they own into JSON-ready data."""
    return {
        "name": owner.name,
        "email": owner.email,
        "address": owner.address,
        "available_minutes": owner.available_minutes,
        "day_start": owner.day_start,
        "day_end": owner.day_end,
        "preferred_types": [t.value for t in owner.preferred_types],
        "pets": [_pet_to_dict(p) for p in owner.pets],
        "cart": [_cart_item_to_dict(i) for i in owner.cart.items],
        "orders": [_order_to_dict(o) for o in owner.orders],
    }


def _owner_from_dict(data: dict) -> Owner:
    """Rebuild an Owner with their pets, cart, and orders."""
    owner = Owner(
        data["name"],
        email=data["email"],
        address=data["address"],
        available_minutes=data["available_minutes"],
        day_start=data["day_start"],
        day_end=data["day_end"],
        preferred_types=[TaskType(v) for v in data["preferred_types"]],
    )
    for pet_data in data["pets"]:
        owner.add_pet(_pet_from_dict(pet_data))  # rejects duplicate pet names
    owner.cart.items = [_cart_item_from_dict(i) for i in data["cart"]]
    # Orders are restored in full, so the next checkout's ID continues from len(orders).
    owner.orders = [_order_from_dict(o) for o in data["orders"]]
    return owner
