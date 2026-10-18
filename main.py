"""PawPal+ CLI demo: builds a sample owner with two pets and prints what the logic layer can do."""

from datetime import date, datetime, time, timedelta

from pawpal_system import (
    Frequency,
    Medication,
    Owner,
    Pet,
    Priority,
    Scheduler,
    SmartCollar,
    Task,
    TaskType,
)

TASK_HEADERS = ["Time", "Pet", "Task", "Type", "Duration", "Priority"]
READING_HEADERS = ["Time", "Heart rate", "SpO2", "Temp", "Breathing", "Sleep",
                   "Steps", "km", "kcal", "Battery"]
# Every column except the first (time) is a number.
RIGHT_ALIGNED = {"Duration", *READING_HEADERS[1:]}
VET_DISCLAIMER = "Not veterinary advice. Contact your vet if you are worried."


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
    # A medication, not a plain task: add_medication stores it in Luna's health
    # profile and schedules its reminder (HIGH priority, 5 min) automatically.
    luna.add_medication(Medication(name="Thyroid pill", dose="2.5 mg", times=["08:00"],
                                   frequency=Frequency.DAILY, start_date=today))
    mochi.add_task(Task("Puzzle feeder", "13:00", today, TaskType.ENRICHMENT,
                        priority=Priority.MEDIUM, duration_minutes=20))

    return owner


def print_heading(title: str) -> None:
    """Print a section heading with an underline."""
    print(f"\n{title}")
    print("=" * len(title))


def format_row(headers: list[str], values: list[str], widths: list[int]) -> str:
    """Pad each value to its column width, right-aligning numeric columns."""
    cells = [
        value.rjust(width) if header in RIGHT_ALIGNED else value.ljust(width)
        for header, value, width in zip(headers, values, widths)
    ]
    return "  ".join(cells).rstrip()


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print rows under headers with lined-up columns and a rule above and below."""
    widths = [max(len(row[i]) for row in [headers, *rows]) for i in range(len(headers))]
    rule = "  ".join("-" * w for w in widths)

    print(format_row(headers, headers, widths))
    print(rule)
    for row in rows:
        print(format_row(headers, row, widths))
    print(rule)


def print_tasks(tasks: list[Task]) -> None:
    """Print tasks as a table with lined-up columns."""
    if not tasks:
        print("No tasks.")
        return

    print_table(TASK_HEADERS, [
        [t.time, t.pet_name, t.description, t.task_type.value,
         f"{t.duration_minutes} min", t.priority.value.upper()]
        for t in tasks
    ])

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

    print_heading("9. Health")
    show_health(owner, today)


def show_health(owner: Owner, today: date) -> None:
    """Pair a seeded collar to Mochi, sync three readings, and show Luna's medication."""
    mochi, luna = owner.get_pet("Mochi"), owner.get_pet("Luna")
    if mochi is None or luna is None:
        return

    collar = SmartCollar("COLLAR-001", seed=42, species=mochi.species)
    mochi.pair_collar(collar)
    print(f"Paired collar {collar.device_id} to {mochi.name} (seed {collar.seed}).")

    rows = []
    for hhmm in (time(8, 0), time(12, 0), time(18, 0)):
        reading = mochi.sync_collar(datetime.combine(today, hhmm))
        if reading is None:
            continue
        # Battery is a collar attribute, not part of the reading: capture it after each sync.
        rows.append([
            f"{reading.timestamp:%H:%M}",
            f"{reading.heart_rate_bpm} bpm",
            f"{reading.spo2_percent:.1f}%",
            f"{reading.temperature_c:.1f} °C",
            f"{reading.respiratory_rate}/min",
            str(reading.sleep_score),
            f"{reading.steps:,}",
            f"{reading.distance_km:.2f}",
            str(reading.calories_burned),
            f"{collar.battery_percent}%",
        ])
    print(f"\n{mochi.name}'s readings today:")
    print_table(READING_HEADERS, rows)

    summary = mochi.health.daily_summary(today)
    print(f"\nDaily summary ({summary['readings']} readings):")
    print(f"- Average heart rate: {summary['avg_heart_rate']} bpm")
    print(f"- Average SpO2: {summary['avg_spo2']}%")
    print(f"- Average temperature: {summary['avg_temperature']} °C")
    print(f"- Average breathing rate: {summary['avg_respiratory_rate']}/min")
    print(f"- Steps: {summary['total_steps']:,} | Distance: {summary['total_distance_km']} km"
          f" | Calories: {summary['total_calories']} kcal")
    print(f"- Latest sleep score: {summary['latest_sleep_score']}")
    print(f"- Symptoms logged: {summary['symptoms']}")

    print(f"\nAlerts for {mochi.name} ({mochi.species}):")
    alerts = mochi.health.check_alerts(mochi.species)
    for alert in alerts:
        print(f"ALERT: {alert}")
    if not alerts:
        print("No alerts.")
    print(VET_DISCLAIMER)

    print(f"\n{luna.name}'s medications:")
    for med in luna.health.medications:
        print(f"- {med.name}, {med.dose}, {med.frequency.value} at {', '.join(med.times)} "
              f"(from {med.start_date:%B %d})")
    print("Reminders added to her schedule by add_medication():")
    print_tasks([t for t in luna.get_tasks() if t.task_type is TaskType.MEDICATION])


if __name__ == "__main__":
    main()
