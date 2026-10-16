"""PawPal+ CLI demo: builds a sample owner with two pets and prints today's schedule."""

from datetime import date, timedelta

from pawpal_system import Frequency, Owner, Pet, Priority, Scheduler, Task, TaskType

HEADERS = ["Time", "Pet", "Task", "Duration", "Priority"]
RIGHT_ALIGNED = {"Duration"}


def build_demo_owner(today: date) -> Owner:
    """Create one owner with a dog and a cat, each with tasks due today."""
    owner = Owner("Jordan", email="jordan@example.com", address="12 Elm Street")

    mochi = Pet("Mochi", "Dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    luna = Pet("Luna", "Cat", "Tabby", age_years=6, weight_kg=4.2)
    owner.add_pet(mochi)
    owner.add_pet(luna)

    # Added out of time order on purpose: the scheduler sorts them.
    mochi.add_task(Task("Evening walk", "18:00", today, TaskType.WALK,
                        priority=Priority.HIGH, duration_minutes=30))
    luna.add_task(Task("Breakfast", "07:00", today, TaskType.FEEDING,
                       priority=Priority.HIGH, duration_minutes=5))
    mochi.add_task(Task("Morning walk", "07:30", today, TaskType.WALK,
                        frequency=Frequency.DAILY, priority=Priority.HIGH,
                        duration_minutes=30))
    luna.add_task(Task("Feather toy play", "19:30", today, TaskType.ENRICHMENT,
                       priority=Priority.LOW, duration_minutes=15))
    mochi.add_task(Task("Brush coat", "12:00", today, TaskType.GROOMING,
                        priority=Priority.MEDIUM, duration_minutes=10))

    return owner


def format_row(values: list[str], widths: list[int]) -> str:
    """Pad each value to its column width, right-aligning numeric columns."""
    cells = [
        value.rjust(width) if header in RIGHT_ALIGNED else value.ljust(width)
        for header, value, width in zip(HEADERS, values, widths)
    ]
    return "  ".join(cells).rstrip()


def print_schedule(title: str, tasks: list[Task]) -> None:
    """Print tasks as a table with lined-up columns."""
    print(title)
    if not tasks:
        print("No tasks scheduled.")
        return

    rows = [
        [t.time, t.pet_name, t.description, f"{t.duration_minutes} min",
         t.priority.value.upper()]
        for t in tasks
    ]
    widths = [max(len(row[i]) for row in [HEADERS, *rows]) for i in range(len(HEADERS))]
    rule = "  ".join("-" * w for w in widths)

    print("=" * len(rule))
    print(format_row(HEADERS, widths))
    print(rule)
    for row in rows:
        print(format_row(row, widths))
    print(rule)

    total = sum(t.duration_minutes for t in tasks)
    print(f"{len(tasks)} tasks, {total} min total")


def main() -> None:
    """Run the PawPal+ demo."""
    today = date.today()
    owner = build_demo_owner(today)
    scheduler = Scheduler(owner)

    print(f"PawPal+ for {owner.name} ({', '.join(p.name for p in owner.pets)})\n")
    print_schedule(f"Today's Schedule - {today:%A, %B %d, %Y}",
                   scheduler.get_todays_schedule(today))

    # Recurrence: completing a DAILY task creates tomorrow's copy.
    print("\nMarking Mochi's daily 'Morning walk' (07:30) complete...")
    upcoming = scheduler.mark_task_complete("Mochi", "Morning walk", "07:30")
    if upcoming is not None:
        print(f"Next occurrence added: '{upcoming.description}' on "
              f"{upcoming.due_date:%A, %B %d} at {upcoming.time}\n")

    tomorrow = today + timedelta(days=1)
    print_schedule(f"Tomorrow's Schedule - {tomorrow:%A, %B %d, %Y}",
                   scheduler.get_todays_schedule(tomorrow))


if __name__ == "__main__":
    main()
