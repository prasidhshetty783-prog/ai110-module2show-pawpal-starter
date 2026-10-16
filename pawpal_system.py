"""PawPal+ logic layer: owners, pets, tasks, scheduling, health tracking, and a food marketplace.

Built from diagrams/uml.mmd. Core scheduling is implemented; health and marketplace
methods are still stubs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Optional

_HHMM_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _validate_hhmm(value: str, field_name: str) -> None:
    """Raise ValueError unless value is a zero-padded 24-hour "HH:MM" string."""
    if not isinstance(value, str) or not _HHMM_PATTERN.match(value):
        raise ValueError(f"{field_name} must be 24-hour 'HH:MM' (e.g. '07:30'), got {value!r}")


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

    def to_tasks(self, pet_name: str) -> list[Task]:
        """Create one HIGH-priority MEDICATION task per time in `times`."""
        raise NotImplementedError


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

    def add_reading(self, reading: HealthReading) -> None:
        """Store a new health reading."""
        raise NotImplementedError

    def add_medication(self, med: Medication) -> None:
        """Start tracking a medication."""
        raise NotImplementedError

    def log_symptom(self, entry: SymptomEntry) -> None:
        """Record a symptom entry."""
        raise NotImplementedError

    def latest_reading(self) -> Optional[HealthReading]:
        """Return the most recent reading, or None if there are none."""
        raise NotImplementedError

    def daily_summary(self, day: date) -> dict:
        """Summarize the readings taken on the given day."""
        raise NotImplementedError

    def check_alerts(self, species: str) -> list[str]:
        """Return readable alerts for vitals outside the species' normal range."""
        raise NotImplementedError


class SmartCollar:
    """A simulated collar that produces repeatable vitals from a seed."""

    def __init__(
        self,
        device_id: str,
        seed: int,
        battery_percent: int = 100,
        is_paired: bool = False,
    ) -> None:
        """Create a collar with a device id and a random seed."""
        self.device_id: str = device_id
        self.seed: int = seed
        self.battery_percent: int = battery_percent
        self.is_paired: bool = is_paired

    def read_vitals(self, at: datetime) -> HealthReading:
        """Generate a plausible health reading timestamped `at`, repeatable from the seed."""
        raise NotImplementedError


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
        raise NotImplementedError

    def pair_collar(self, collar: SmartCollar) -> None:
        """Pair a smart collar with this pet."""
        raise NotImplementedError

    def sync_collar(self, at: datetime) -> Optional[HealthReading]:
        """Read vitals from the paired collar, or return None if no collar is paired."""
        raise NotImplementedError


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
        raise NotImplementedError

    def detect_conflicts(self, day: date) -> list[str]:
        """Return a warning for each set of tasks sharing the same date and time."""
        raise NotImplementedError

    def mark_task_complete(self, pet_name: str, description: str, time: str) -> Optional[Task]:
        """Complete the earliest-due incomplete match and return its next occurrence, if any."""
        pet = self.owner.get_pet(pet_name)
        if pet is None:
            return None
        task = pet._find_task(description, time)
        if task is None:
            return None
        upcoming = task.mark_complete()
        if upcoming is None:
            return None
        # Same check as Pet._is_duplicate: if the next occurrence is already there
        # (completed or not), hand it back instead of adding a copy.
        existing = next(
            (t for t in pet.tasks
             if t.description == upcoming.description
             and t.time == upcoming.time
             and t.due_date == upcoming.due_date),
            None,
        )
        if existing is not None:
            return existing
        pet.add_task(upcoming)
        return upcoming

    def build_daily_plan(self, day: date) -> list[Task]:
        """Choose the day's tasks that fit the owner's time and hours, sorted by time."""
        raise NotImplementedError

    def skipped_tasks(self, day: date) -> list[Task]:
        """Return the day's tasks that did not make the plan."""
        raise NotImplementedError

    def explain_plan(self, day: date) -> list[str]:
        """Return one plain-English reason for each chosen or skipped task."""
        raise NotImplementedError


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
