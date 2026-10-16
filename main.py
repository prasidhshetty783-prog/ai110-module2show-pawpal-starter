"""PawPal+ CLI demo: builds a sample owner with two pets and prints what the scheduler can do."""

from datetime import date, timedelta

from pawpal_system import Frequency, Owner, Pet, Priority, Scheduler, Task, TaskType

HEADERS = ["Time", "Pet", "Task", "Type", "Duration", "Priority"]
RIGHT_ALIGNED = {"Duration"}


def build_demo_owner(today: date) -> Owner:
    """Create one busy owner with a dog and a cat and more tasks than fit in a day."""
    owner = Owner(
        "Jordan",
        email="jordan@example.com",
        address="12 Elm Street",
        available_minutes=90,
        preferred_types=[TaskType.WALK],
    )

    mochi = Pet("Mochi", "Dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    luna = Pet("Luna", "Cat", "Tabby", age_years=6, weight_kg=4.2)
    owner.add_pet(mochi)
    owner.add_pet(luna)

    # Added out of time order on purpose: the scheduler sorts them.
    # 170 min of tasks for a 90 min budget, so some must be skipped.
    mochi.add_task(Task("Evening walk", "18:00", today, TaskType.WALK,
                        priority=Priority.HIGH, duration_minutes=30))
    luna.add_task(Task("Feather toy play", "19:30", today, TaskType.ENRICHMENT,
                       priority=Priority.LOW, duration_minutes=10))
    mochi.add_task(Task("Brush coat", "12:00", today, TaskType.GROOMING,
                        priority=Priority.MEDIUM, duration_minutes=10))
    # Same time as Mochi's morning walk: a conflict across two pets.
    luna.add_task(Task("Breakfast", "07:30", today, TaskType.FEEDING,
                       priority=Priority.HIGH, duration_minutes=5))
    mochi.add_task(Task("Bath", "16:00", today, TaskType.GROOMING,
                        priority=Priority.MEDIUM, duration_minutes=40))
    # Ends at 21:05, after the owner's 21:00 day end.
    luna.add_task(Task("Nail trim", "20:45", today, TaskType.GROOMING,
                       priority=Priority.LOW, duration_minutes=20))
    mochi.add_task(Task("Morning walk", "07:30", today, TaskType.WALK,
                        frequency=Frequency.DAILY, priority=Priority.HIGH,
                        duration_minutes=30))
    luna.add_task(Task("Thyroid pill", "08:00", today, TaskType.MEDICATION,
                       priority=Priority.HIGH, duration_minutes=5))
    mochi.add_task(Task("Puzzle feeder", "13:00", today, TaskType.ENRICHMENT,
                        priority=Priority.MEDIUM, duration_minutes=20))

    return owner


def print_heading(title: str) -> None:
    """Print a section heading with an underline."""
    print(f"\n{title}")
    print("=" * len(title))


def format_row(values: list[str], widths: list[int]) -> str:
    """Pad each value to its column width, right-aligning numeric columns."""
    cells = [
        value.rjust(width) if header in RIGHT_ALIGNED else value.ljust(width)
        for header, value, width in zip(HEADERS, values, widths)
    ]
    return "  ".join(cells).rstrip()


def print_tasks(tasks: list[Task]) -> None:
    """Print tasks as a table with lined-up columns."""
    if not tasks:
        print("No tasks.")
        return

    rows = [
        [t.time, t.pet_name, t.description, t.task_type.value,
         f"{t.duration_minutes} min", t.priority.value.upper()]
        for t in tasks
    ]
    widths = [max(len(row[i]) for row in [HEADERS, *rows]) for i in range(len(HEADERS))]
    rule = "  ".join("-" * w for w in widths)

    print(format_row(HEADERS, widths))
    print(rule)
    for row in rows:
        print(format_row(row, widths))
    print(rule)

    total = sum(t.duration_minutes for t in tasks)
    print(f"{len(tasks)} task{'s' if len(tasks) != 1 else ''}, {total} min total")


def main() -> None:
    """Run the PawPal+ demo."""
    today = date.today()
    owner = build_demo_owner(today)
    scheduler = Scheduler(owner)
    all_tasks = owner.get_all_tasks()

    print(f"PawPal+ for {owner.name} ({', '.join(p.name for p in owner.pets)}) "
          f"- {today:%A, %B %d, %Y}")
    print(f"Available: {owner.available_minutes} min | "
          f"Hours: {owner.day_start}-{owner.day_end} | "
          f"Prefers: {', '.join(t.value for t in owner.preferred_types)}")

    print_heading("1. All tasks, sorted by time")
    print_tasks(scheduler.sort_by_time(all_tasks))

    print_heading("2. All tasks, sorted by priority (then preferred type, then time)")
    print_tasks(scheduler.sort_by_priority(all_tasks))

    print_heading("3. Filtered to one pet: Luna")
    print_tasks(scheduler.sort_by_time(scheduler.filter_tasks(pet_name="Luna")))

    print_heading("4. Conflict warnings")
    conflicts = scheduler.detect_conflicts(today)
    for warning in conflicts:
        print(f"WARNING: {warning}")
    if not conflicts:
        print("No conflicts.")

    print_heading("5. Today's plan")
    plan = scheduler.build_daily_plan(today)
    print_tasks(plan)
    used = sum(t.duration_minutes for t in plan)
    print(f"Minutes used: {used} of {owner.available_minutes} available")

    print_heading("6. Skipped tasks")
    print_tasks(scheduler.skipped_tasks(today))

    print_heading("7. Why each task was planned or skipped")
    for line in scheduler.explain_plan(today):
        print(f"- {line}")

    # Recurrence: completing a DAILY task creates tomorrow's copy.
    print_heading("8. Recurring task rolls over")
    print("Marking Mochi's daily 'Morning walk' (07:30) complete...")
    upcoming = scheduler.mark_task_complete("Mochi", "Morning walk", "07:30")
    if upcoming is not None:
        print(f"Next occurrence added: '{upcoming.description}' on "
              f"{upcoming.due_date:%A, %B %d} at {upcoming.time}")

    tomorrow = today + timedelta(days=1)
    print(f"\nTomorrow's tasks ({tomorrow:%A, %B %d}):")
    print_tasks(scheduler.get_todays_schedule(tomorrow))


if __name__ == "__main__":
    main()
