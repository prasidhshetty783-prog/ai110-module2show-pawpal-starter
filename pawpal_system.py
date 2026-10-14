"""PawPal+ logic layer: owners, pets, tasks, scheduling, health tracking, and a food marketplace.

Skeleton generated from diagrams/uml.mmd. Method bodies are not implemented yet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Priority(Enum):
    """How important a task is."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Frequency(Enum):
    """How often a task or medication repeats."""

    ONCE = "once"
    DAILY = "daily"
    WEEKLY = "weekly"


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
    CANCELLED = "cancelled"


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

    def read_vitals(self) -> HealthReading:
        """Generate a plausible health reading from the collar's seed."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Core Scheduling
# ---------------------------------------------------------------------------

@dataclass
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

    def mark_complete(self) -> Optional[Task]:
        """Mark this task done and return its next occurrence, if any."""
        raise NotImplementedError

    def next_occurrence(self) -> Optional[Task]:
        """Return the next copy of a recurring task, or None for a one-time task."""
        raise NotImplementedError


@dataclass
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

    def add_task(self, task: Task) -> None:
        """Add a task to this pet and set its pet_name."""
        raise NotImplementedError

    def remove_task(self, description: str, time: str) -> bool:
        """Remove the earliest-due incomplete matching task; return True if removed."""
        raise NotImplementedError

    def get_tasks(self) -> list[Task]:
        """Return this pet's tasks."""
        raise NotImplementedError

    def pair_collar(self, collar: SmartCollar) -> None:
        """Pair a smart collar with this pet."""
        raise NotImplementedError

    def sync_collar(self) -> Optional[HealthReading]:
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
        self.name: str = name
        self.email: str = email
        self.address: str = address
        self.available_minutes: int = available_minutes
        self.day_start: str = day_start
        self.day_end: str = day_end
        self.preferred_types: list[TaskType] = (
            preferred_types if preferred_types is not None else []
        )
        self.pets: list[Pet] = []
        self.cart: Cart = Cart()
        self.orders: list[Order] = []

    def add_pet(self, pet: Pet) -> None:
        """Add a pet to this owner."""
        raise NotImplementedError

    def remove_pet(self, name: str) -> bool:
        """Remove a pet by name; return True if one was removed."""
        raise NotImplementedError

    def get_pet(self, name: str) -> Optional[Pet]:
        """Return the pet with this name, or None if not found."""
        raise NotImplementedError

    def get_all_tasks(self) -> list[Task]:
        """Return every task across all of this owner's pets."""
        raise NotImplementedError

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
        raise NotImplementedError

    def sort_by_time(self, tasks: list[Task]) -> list[Task]:
        """Return the tasks sorted by their HH:MM time."""
        raise NotImplementedError

    def sort_by_priority(self, tasks: list[Task]) -> list[Task]:
        """Return the tasks sorted with HIGH priority first."""
        raise NotImplementedError

    def filter_tasks(self, pet_name: str, completed: bool) -> list[Task]:
        """Return tasks for one pet with the given completion status."""
        raise NotImplementedError

    def detect_conflicts(self, day: date) -> list[str]:
        """Return a warning for each set of tasks sharing the same date and time."""
        raise NotImplementedError

    def mark_task_complete(self, pet_name: str, description: str, time: str) -> Optional[Task]:
        """Complete the earliest-due incomplete match and return its next occurrence, if any."""
        raise NotImplementedError

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

    def checkout(self, owner: Owner, payment: MockPayment) -> Order:
        """Charge the payment, create an Order, add it to the owner, and clear the cart."""
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
