"""PawPal+ CLI demo: builds a sample owner with two pets and prints what the logic layer can do."""

import io
import sys
from datetime import date, datetime, time, timedelta

from tabulate import tabulate

from pawpal_system import (
    SAMPLE_CATALOG,
    Frequency,
    HealthProfile,
    Marketplace,
    Medication,
    MockPayment,
    Owner,
    Pet,
    Priority,
    Scheduler,
    SmartCollar,
    Task,
    TaskType,
)

# Windows consoles default to cp1252, which cannot encode emoji or the table borders
# once output is piped or redirected. Force UTF-8 so the demo runs in PowerShell.
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding="utf-8")

TABLE_FORMAT = "rounded_outline"

# Emoji go in headings and status lines only, never in table cells: without the
# optional wcwidth package, tabulate counts an emoji as one column, but terminals
# draw it two wide, which would push that row's border out of line.
PAW = "🐾"
SPECIES_ICONS = {"dog": "🐕", "cat": "🐈"}
PLANNED = "✅"
CAN_WAIT = "⏳"
MEDICATION = "💊"
WARNING = "⚠️"
HEALTH = "🩺"
SHOP = "🛒"
ORDER = "📦"
RECURRING = "🔁"

TASK_HEADERS = ["Time", "Pet", "Task", "Type", "Duration", "Priority"]
READING_HEADERS = ["Time", "Heart rate", "SpO2", "Temp", "Breathing", "Sleep",
                   "Steps", "km", "kcal", "Battery"]
# Every column except the first (time) is a number.
COMPARE_HEADERS = ["ID", "Brand", "Name", "Stage", "Price", "Rating", "kcal/cup"]
CART_HEADERS = ["ID", "Product", "Qty", "Price", "Subtotal"]
SUMMARY_HEADERS = ["Metric", "Value"]
MEDICATION_HEADERS = ["Medication", "Dose", "Frequency", "Times", "From"]
PRODUCT_HEADERS = ["ID", "Product", "Price"]
EXCLUDED_HEADERS = ["ID", "Product", "Reason"]
RIGHT_ALIGNED = {"Duration", *READING_HEADERS[1:], "Price", "Rating", "kcal/cup", "Qty",
                 "Subtotal", "Value"}
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

    # Each pet has an allergy that rules out some of its own species' food in the shop.
    mochi = Pet("Mochi", "Dog", "Shiba Inu", age_years=3, weight_kg=10.5,
                health=HealthProfile(conditions=["sensitive skin"], allergies=["chicken"]))
    luna = Pet("Luna", "Cat", "Tabby", age_years=6, weight_kg=4.2,
               health=HealthProfile(conditions=["urinary health"], allergies=["fish"]))
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


def species_icon(pet: Pet) -> str:
    """Return the emoji for a pet's species, or a paw print for any other species."""
    return SPECIES_ICONS.get(pet.species, PAW)


def print_heading(icon: str, title: str) -> None:
    """Print an emoji section heading with an underline."""
    print(f"\n{icon} {title}")
    # The emoji is drawn two columns wide, plus one for the space after it.
    print("=" * (len(title) + 3))


def print_table(headers: list[str], rows: list[list[str]]) -> None:
    """Print rows under headers in a rounded box, right-aligning numeric columns."""
    colalign = tuple("right" if h in RIGHT_ALIGNED else "left" for h in headers)
    # Cells are already formatted strings; numparse would turn "0.40" back into 0.4.
    print(tabulate(rows, headers=headers, tablefmt=TABLE_FORMAT, colalign=colalign,
                   disable_numparse=True))


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

    pets = ", ".join(f"{species_icon(p)} {p.name}" for p in owner.pets)
    print(f"{PAW} PawPal+ for {owner.name} ({pets}) - {today:%A, %B %d, %Y}")
    print(f"Available: {owner.available_minutes} min | "
          f"Hours: {owner.day_start}-{owner.day_end} | "
          f"Prefers: {', '.join(t.value for t in owner.preferred_types)}")

    print_heading(PAW, "1. All tasks, sorted by time")
    print_tasks(scheduler.sort_by_time(all_tasks))

    print_heading(PAW, "2. All tasks, sorted by priority (then preferred type, then time)")
    print_tasks(scheduler.sort_by_priority(all_tasks))

    luna = owner.get_pet("Luna")
    print_heading(species_icon(luna) if luna else PAW, "3. Filtered to one pet: Luna")
    print_tasks(scheduler.sort_by_time(scheduler.filter_tasks(pet_name="Luna")))

    print_heading(WARNING, "4. Conflict warnings")
    conflicts = scheduler.detect_conflicts(today)
    for warning in conflicts:
        print(f"{WARNING} {warning}")
    if not conflicts:
        print(f"{PLANNED} No conflicts.")

    print_heading(PLANNED, "5. Today's plan")
    plan = scheduler.build_daily_plan(today)
    print_tasks(plan)
    used = sum(t.duration_minutes for t in plan)
    print(f"{PLANNED} Minutes used: {used} of {owner.available_minutes} available")

    print_heading(CAN_WAIT, "6. Skipped tasks (these can wait)")
    skipped = scheduler.skipped_tasks(today)
    print_tasks(skipped)

    print_heading(PAW, "7. Why each task was planned or skipped")
    # explain_plan() lists chosen + skipped sorted by time; the same sort pairs each
    # line with its task, so the icon comes from the task, not from parsing the text.
    planned = set(plan)
    explained = scheduler.sort_by_time(plan + skipped)
    for task, line in zip(explained, scheduler.explain_plan(today)):
        if task.task_type is TaskType.MEDICATION:
            icon = MEDICATION
        else:
            icon = PLANNED if task in planned else CAN_WAIT
        print(f"{icon} {line}")

    # Recurrence: completing a DAILY task creates tomorrow's copy.
    print_heading(RECURRING, "8. Recurring task rolls over")
    print("Marking Mochi's daily 'Morning walk' (07:30) complete...")
    upcoming = scheduler.mark_task_complete("Mochi", "Morning walk", "07:30")
    if upcoming is not None:
        print(f"{RECURRING} Next occurrence added: '{upcoming.description}' on "
              f"{upcoming.due_date:%A, %B %d} at {upcoming.time}")

    tomorrow = today + timedelta(days=1)
    print(f"\nTomorrow's tasks ({tomorrow:%A, %B %d}):")
    print_tasks(scheduler.get_todays_schedule(tomorrow))

    print_heading(HEALTH, "9. Health")
    show_health(owner, today)

    print_heading(SHOP, "10. Shop")
    show_shop(owner, scheduler, today)


def show_health(owner: Owner, today: date) -> None:
    """Pair a seeded collar to Mochi, sync three readings, and show Luna's medication."""
    mochi, luna = owner.get_pet("Mochi"), owner.get_pet("Luna")
    if mochi is None or luna is None:
        return

    collar = SmartCollar("COLLAR-001", seed=42, species=mochi.species)
    mochi.pair_collar(collar)
    print(f"{species_icon(mochi)} Paired collar {collar.device_id} to {mochi.name} "
          f"(seed {collar.seed}).")

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
    print(f"\n{HEALTH} Daily summary ({summary['readings']} readings):")
    print_table(SUMMARY_HEADERS, [
        ["Average heart rate", f"{summary['avg_heart_rate']} bpm"],
        ["Average SpO2", f"{summary['avg_spo2']}%"],
        ["Average temperature", f"{summary['avg_temperature']} °C"],
        ["Average breathing rate", f"{summary['avg_respiratory_rate']}/min"],
        ["Steps", f"{summary['total_steps']:,}"],
        ["Distance", f"{summary['total_distance_km']} km"],
        ["Calories", f"{summary['total_calories']} kcal"],
        ["Latest sleep score", str(summary["latest_sleep_score"])],
        ["Symptoms logged", str(summary["symptoms"])],
    ])

    print(f"\n{WARNING} Alerts for {mochi.name} ({mochi.species}):")
    alerts = mochi.health.check_alerts(mochi.species)
    for alert in alerts:
        print(f"{WARNING} ALERT: {alert}")
    if not alerts:
        print(f"{PLANNED} No alerts.")
    print(VET_DISCLAIMER)

    print(f"\n{MEDICATION} {species_icon(luna)} {luna.name}'s medications:")
    print_table(MEDICATION_HEADERS, [
        [med.name, med.dose, med.frequency.value, ", ".join(med.times),
         f"{med.start_date:%B %d}"]
        for med in luna.health.medications
    ])
    print(f"{MEDICATION} Reminders added to her schedule by add_medication():")
    print_tasks([t for t in luna.get_tasks() if t.task_type is TaskType.MEDICATION])


def show_shop(owner: Owner, scheduler: Scheduler, today: date) -> None:
    """Recommend safe food for each pet, compare products, and place a simulated order."""
    market = Marketplace(SAMPLE_CATALOG)

    for pet in owner.pets:
        print(f"\n{species_icon(pet)} Top 3 for {pet.name} ({pet.species}, conditions: "
              f"{', '.join(pet.health.conditions) or 'none'}, allergies: "
              f"{', '.join(pet.health.allergies) or 'none'}):")
        for rank, product in enumerate(market.recommend_for(pet, 3), start=1):
            print(f"{rank}. [{product.product_id}] {product.brand} {product.name}, "
                  f"${product.price:.2f}: score {market.score(product, pet):.2f}")
            for line in market.explain_recommendation(product, pet):
                print(f"   - {line}")

        # Same-species products that never appear in any recommendation were excluded.
        safe = market.recommend_for(pet, len(market.catalog))
        excluded = [p for p in market.search(pet.species, "") if p not in safe]
        print(f"{WARNING} Excluded for {pet.name}:")
        rows = []
        for product in excluded:
            [reason] = market.explain_recommendation(product, pet)
            rows.append([product.product_id, f"{product.brand} {product.name}", reason])
        print_table(EXCLUDED_HEADERS, rows)

    print(f'\n{SHOP} Search dog food for "tailwind":')
    print_table(PRODUCT_HEADERS, [
        [p.product_id, f"{p.brand} {p.name}", f"${p.price:.2f}"]
        for p in market.search("dog", "tailwind")
    ])

    print(f"\n{SHOP} Compare D01, D06, C03 (kcal is shown here only; it is not scored):")
    print_table(COMPARE_HEADERS, [
        [row["product_id"], row["brand"], row["name"], row["life_stage"],
         f"${row['price']:.2f}", f"{row['rating']:g}", str(row["kcal_per_cup"])]
        for row in market.compare(["D01", "D06", "C03"])
    ])

    mochi = owner.get_pet("Mochi")
    if mochi is None:
        return
    favourite = market.recommend_for(mochi, 1)[0]
    cart = owner.cart
    cart.add_item(favourite, 1)
    cart.add_item(favourite, 1)  # same product again: quantity becomes 2, not a new line
    cart.add_item(market.search("dog", "lite turkey")[0], 1)
    print(f"\n{SHOP} Cart (the first product was added twice, so its quantity merged):")
    print_table(CART_HEADERS, [
        [item.product.product_id, f"{item.product.brand} {item.product.name}",
         str(item.quantity), f"${item.product.price:.2f}", f"${item.subtotal():.2f}"]
        for item in cart.items
    ])
    print(f"Total: ${cart.total():.2f}")

    # MockPayment is simulated: no card number or other payment detail is asked for or stored.
    order = cart.checkout(owner, MockPayment(), mochi.name, today)
    print(f"\n{ORDER} Order {order.order_id} placed on {order.placed_on:%B %d} for ${order.total:.2f}, "
          f"delivering to {order.delivery_address} on {order.delivery_date:%A, %B %d}.")
    print(f"Cart after checkout: {len(cart.items)} items. "
          f"Order still holds {len(order.items)} line items.")

    print(f"\nTasks on {order.delivery_date:%A, %B %d} (checkout added the delivery):")
    print_tasks(scheduler.get_todays_schedule(order.delivery_date))

    print(f"\n{ORDER} Order status:")
    print(f"{ORDER} {order.status.value}")
    while order.advance_status():
        print(f"{ORDER} {order.status.value}")
    print(f"advance_status() at {order.status.value} returns False.")


if __name__ == "__main__":
    main()
