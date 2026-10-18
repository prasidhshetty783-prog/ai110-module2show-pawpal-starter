"""PawPal+ Streamlit UI. All logic lives in pawpal_system.py; this file only displays it."""

from __future__ import annotations

from datetime import date, datetime, time as dt_time
from pathlib import Path

import streamlit as st

from pawpal_system import (
    SAMPLE_CATALOG,
    VITAL_RANGES,
    FoodProduct,
    Frequency,
    HealthReading,
    Marketplace,
    Medication,
    MockPayment,
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

st.set_page_config(page_title="PawPal+", page_icon="🐾", layout="centered")

# Task types a user can create by hand. DELIVERY tasks only come from checkout.
UI_TASK_TYPES = [
    TaskType.WALK.value,
    TaskType.FEEDING.value,
    TaskType.MEDICATION.value,
    TaskType.ENRICHMENT.value,
    TaskType.GROOMING.value,
    TaskType.APPOINTMENT.value,
]
PRIORITIES = [p.value for p in Priority]
FREQUENCIES = [f.value for f in Frequency]
SEVERITIES = [s.value for s in Severity]
SPECIES = ["dog", "cat", "other"]
DATA_FILE = "data.json"
TABS = ["Schedule", "Health", "Shop"]
MAX_READINGS_SHOWN = 10

# How each daily_summary() key reads in the Health tab: (label, unit suffix).
SUMMARY_LABELS = [
    ("readings", "Readings", ""),
    ("avg_heart_rate", "Average heart rate", " bpm"),
    ("avg_spo2", "Average SpO2", "%"),
    ("avg_temperature", "Average temperature", " °C"),
    ("avg_respiratory_rate", "Average breathing rate", "/min"),
    ("total_steps", "Steps", ""),
    ("total_distance_km", "Distance", " km"),
    ("total_calories", "Calories burned", " kcal"),
    ("latest_sleep_score", "Latest sleep score", "/100"),
    ("symptoms", "Symptoms logged", ""),
]

if "owner" not in st.session_state:
    loaded_owner = None
    if Path(DATA_FILE).exists():
        try:
            loaded_owner = Owner.load_from_json(DATA_FILE)
        except (ValueError, KeyError, TypeError) as exc:  # corrupt or hand-edited file
            st.session_state["_flash"] = (
                "main",
                "warning",
                f"Couldn't load {DATA_FILE} ({exc}). Starting fresh; saving will overwrite it.",
            )
    st.session_state["owner"] = loaded_owner or Owner(name="Jordan")
owner: Owner = st.session_state["owner"]
today = date.today()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_time(hhmm: str) -> dt_time:
    """Convert an "HH:MM" string into a datetime.time for st.time_input."""
    return datetime.strptime(hhmm, "%H:%M").time()


def _hhmm(value: dt_time) -> str:
    """Convert a datetime.time into the zero-padded "HH:MM" string the logic layer expects."""
    return value.strftime("%H:%M")


def _flash(message: str, where: str = "main", kind: str = "success") -> None:
    """Remember a message for the next run, then rerun so every section shows fresh data.

    `where` is "main" (above the tabs) or a tab name, so the message appears
    next to the form that caused it.
    """
    st.session_state["_flash"] = (where, kind, message)
    st.rerun()


def _show_flash(where: str = "main") -> None:
    """Show (once) the message saved by _flash, if it belongs here."""
    flash = st.session_state.get("_flash")
    if flash is not None and flash[0] == where:
        del st.session_state["_flash"]
        _, kind, message = flash
        getattr(st, kind)(message)


def _split_csv(text: str) -> list[str]:
    """Split comma-separated text into trimmed, non-empty parts."""
    return [part.strip() for part in text.split(",") if part.strip()]


def _clean_terms(text: str) -> list[str]:
    """Split comma-separated text into lowercase terms, dropping repeats but keeping order."""
    return list(dict.fromkeys(part.lower() for part in _split_csv(text)))


def _pick_pet(label: str, key: str) -> Pet:
    """Show a pet dropdown and return the chosen pet (owner.pets must not be empty)."""
    name = st.selectbox(label, [p.name for p in owner.pets], key=key)
    return owner.get_pet(name) or owner.pets[0]


def _task_rows(tasks: list[Task], include_pet: bool) -> list[dict]:
    """Turn tasks into plain dicts for st.table."""
    rows = []
    for t in tasks:
        row = {"Date": t.due_date.isoformat(), "Time": t.time}
        if include_pet:
            row["Pet"] = t.pet_name
        row.update(
            {
                "Task": t.description,
                "Type": t.task_type.value,
                "Minutes": t.duration_minutes,
                "Priority": t.priority.value,
                "Repeats": t.frequency.value,
                "Done": "✓" if t.completed else "",
            }
        )
        rows.append(row)
    return rows


def _editable_tasks(pet: Pet) -> list[Task]:
    """Return, per description + time, the earliest-due incomplete task.

    These are exactly the tasks Pet.update_task() and Pet.remove_task() act on,
    so the user can never pick one task and have a different one change.
    """
    earliest: dict[tuple[str, str], Task] = {}
    for t in pet.get_tasks():
        if t.completed:
            continue
        key = (t.description, t.time)
        if key not in earliest or t.due_date < earliest[key].due_date:
            earliest[key] = t
    return sorted(earliest.values(), key=lambda t: (t.due_date, t.time))


def _task_label(task: Task) -> str:
    """Return a short label for a task in a dropdown."""
    return f"{task.due_date.isoformat()} {task.time} · {task.description} ({task.task_type.value})"


def _skip_reason(task: Task, explanations: list[str]) -> str:
    """Find a skipped task's reason among the explain_plan() lines.

    Each line starts with the task's time, description, pet, and minutes, and a pet
    can't have two tasks with the same description and time on one day, so the
    prefix picks out exactly one line.
    """
    prefix = (
        f"{task.time} {task.description} ({task.pet_name}, "
        f"{task.duration_minutes} min): skipped. "
    )
    return next(
        (line.removeprefix(prefix) for line in explanations if line.startswith(prefix)), ""
    )


def _reading_rows(readings: list[HealthReading]) -> list[dict]:
    """Turn collar readings into plain dicts for st.table."""
    return [
        {
            "Time": f"{r.timestamp:%Y-%m-%d %H:%M:%S}",
            "Heart rate": f"{r.heart_rate_bpm} bpm",
            "SpO2": f"{r.spo2_percent}%",
            "Temp": f"{r.temperature_c} °C",
            "Breathing": f"{r.respiratory_rate}/min",
            "Sleep": r.sleep_score,
            "Steps": r.steps,
            "Km": f"{r.distance_km}",
            "Kcal": r.calories_burned,
        }
        for r in readings
    ]


def _summary_rows(summary: dict) -> list[dict]:
    """Turn a daily_summary() dict into Measure / Value rows for st.table."""
    return [
        {
            "Measure": label,
            "Value": "–" if summary[key] is None else f"{summary[key]}{unit}",
        }
        for key, label, unit in SUMMARY_LABELS
    ]


def _product_label(product: FoodProduct) -> str:
    """Return a short label for a product in a dropdown (no "$": labels render Markdown)."""
    return f"{product.brand} · {product.name} ({product.price:.2f})"


def _escape_dollars(text: str) -> str:
    """Escape "$" so Streamlit's Markdown doesn't read prices as LaTeX math."""
    return text.replace("$", "\\$")


def _money(amount: float) -> str:
    """Format an amount as dollars for Markdown text."""
    return _escape_dollars(f"${amount:,.2f}")


# ---------------------------------------------------------------------------
# Sidebar: owner info, constraints, add pet
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("Owner")
    owner.name = st.text_input("Name", value=owner.name, key="owner_name")
    owner.email = st.text_input("Email", value=owner.email, key="owner_email")
    owner.address = st.text_input("Address", value=owner.address, key="owner_address")

    st.subheader("Today's constraints")
    owner.available_minutes = int(
        st.number_input(
            "Available minutes today",
            min_value=0,
            max_value=1440,
            value=owner.available_minutes,
            step=15,
            key="owner_minutes",
        )
    )
    owner.day_start = _hhmm(
        st.time_input("Day start", value=_to_time(owner.day_start), key="owner_day_start")
    )
    owner.day_end = _hhmm(
        st.time_input("Day end", value=_to_time(owner.day_end), key="owner_day_end")
    )
    if owner.day_end <= owner.day_start:
        st.warning("Day end is not after day start, so only medication tasks can be planned.")

    preferred = st.multiselect(
        "Preferred task types",
        options=UI_TASK_TYPES,
        default=[t.value for t in owner.preferred_types if t.value in UI_TASK_TYPES],
        help="When time is tight, these types are planned first.",
        key="owner_preferred",
    )
    owner.preferred_types = [TaskType(v) for v in preferred]

    st.divider()
    st.header("Add a pet")
    with st.form("add_pet_form", clear_on_submit=True):
        pet_name = st.text_input("Pet name")
        species = st.selectbox("Species", SPECIES)
        breed = st.text_input("Breed")
        age = st.number_input("Age (years)", min_value=0.0, max_value=40.0, value=1.0, step=0.5)
        weight = st.number_input(
            "Weight (kg)", min_value=0.1, max_value=150.0, value=5.0, step=0.5
        )
        add_pet_clicked = st.form_submit_button("Add pet", icon=":material/pets:")

    if add_pet_clicked:
        clean_name = pet_name.strip()
        if not clean_name:
            st.error("Give your pet a name first.")
        else:
            try:
                owner.add_pet(
                    Pet(
                        name=clean_name,
                        species=species,
                        breed=breed.strip(),
                        age_years=float(age),
                        weight_kg=float(weight),
                    )
                )
            except ValueError:
                st.error(f"You already have a pet named {clean_name}. Pick a different name.")
            else:
                _flash(f"Added {clean_name}.")

    st.divider()
    if st.button("Save", type="primary", icon=":material/save:", width="stretch"):
        # The sidebar allows end <= start (with a warning), but Owner would reject
        # that window on the next load, so don't write a file that can't be read back.
        if owner.day_end <= owner.day_start:
            st.error("Set your day end after your day start before saving.")
        else:
            try:
                owner.save_to_json(DATA_FILE)
            except OSError as exc:
                st.error(f"Couldn't save {DATA_FILE}: {exc}")
            else:
                st.success(f"Saved to {DATA_FILE}.")


# ---------------------------------------------------------------------------
# Main page: Schedule | Health | Shop
# ---------------------------------------------------------------------------

st.title("🐾 PawPal+")
st.caption(f"Pet care planner for {owner.name or 'you'} · {today:%A, %B %d, %Y}")
_show_flash()

# key + on_change="rerun" make the tabs remember the open tab, so the st.rerun()
# after every action lands the user back on the tab they were using.
schedule_tab, health_tab, shop_tab = st.tabs(TABS, key="main_tab", on_change="rerun")


# ===========================================================================
# Schedule tab
# ===========================================================================

with schedule_tab:
    _show_flash("Schedule")

    # --- Add a task ---------------------------------------------------------
    st.subheader("Add a task")
    if not owner.pets:
        st.info("Add a pet in the sidebar to start adding tasks.")
    else:
        with st.form("add_task_form", clear_on_submit=True):
            task_pet_name = st.selectbox("Pet", [p.name for p in owner.pets])
            description = st.text_input("Description", placeholder="e.g. Morning walk")
            left, right = st.columns(2)
            task_type = left.selectbox("Task type", UI_TASK_TYPES)
            priority = right.selectbox("Priority", PRIORITIES, index=PRIORITIES.index("medium"))
            due_date = left.date_input("Due date", value=today)
            task_time = right.time_input("Time", value=dt_time(8, 0), step=300)
            duration = left.number_input(
                "Duration (minutes)", min_value=1, max_value=240, value=15
            )
            frequency = right.selectbox("Frequency", FREQUENCIES)
            add_task_clicked = st.form_submit_button("Add task", icon=":material/add_task:")

        if add_task_clicked:
            clean_description = description.strip()
            pet = owner.get_pet(task_pet_name)
            if not clean_description:
                st.error("Describe the task first.")
            elif pet is None:
                st.error("That pet no longer exists.")
            else:
                try:
                    pet.add_task(
                        Task(
                            description=clean_description,
                            time=_hhmm(task_time),
                            due_date=due_date,
                            task_type=TaskType(task_type),
                            frequency=Frequency(frequency),
                            priority=Priority(priority),
                            duration_minutes=int(duration),
                        )
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _flash(f"Added '{clean_description}' for {pet.name}.", "Schedule")

    # --- Task list ----------------------------------------------------------
    st.divider()
    st.subheader("Tasks")
    if not owner.pets:
        st.caption("No pets yet.")
    for pet in owner.pets:
        st.markdown(f"**{pet.name}** · {pet.species}, {pet.breed or 'breed not set'}")
        pet_tasks = sorted(pet.get_tasks(), key=lambda t: (t.due_date, t.time))
        if pet_tasks:
            st.table(
                _task_rows(pet_tasks, include_pet=False),
                hide_index=True,
                alt=f"{pet.name}'s tasks",
            )
        else:
            st.caption("No tasks yet.")

    # --- Edit or remove a task ----------------------------------------------
    pets_with_open_tasks = [p for p in owner.pets if _editable_tasks(p)]
    if pets_with_open_tasks:
        st.divider()
        st.subheader("Edit or remove a task")
        edit_pet_name = st.selectbox(
            "Pet", [p.name for p in pets_with_open_tasks], key="edit_pet_name"
        )
        edit_pet = owner.get_pet(edit_pet_name)
        targets = _editable_tasks(edit_pet)
        chosen = st.selectbox(
            "Task",
            options=range(len(targets)),
            format_func=lambda i: _task_label(targets[i]),
            key=f"edit_task_index::{edit_pet.name}",
            help="For a repeating task, this is its earliest open occurrence.",
        )
        task = targets[chosen]

        # Keys depend on the chosen task, so switching tasks refills the form.
        k = f"edit::{edit_pet.name}::{task.description}::{task.time}::{task.due_date}"
        with st.form(f"{k}::form"):
            new_description = st.text_input(
                "Description", value=task.description, key=f"{k}::desc"
            )
            left, right = st.columns(2)
            new_type = left.selectbox(
                "Task type",
                UI_TASK_TYPES,
                index=UI_TASK_TYPES.index(task.task_type.value)
                if task.task_type.value in UI_TASK_TYPES
                else 0,
                key=f"{k}::type",
            )
            new_priority = right.selectbox(
                "Priority",
                PRIORITIES,
                index=PRIORITIES.index(task.priority.value),
                key=f"{k}::prio",
            )
            new_due = left.date_input("Due date", value=task.due_date, key=f"{k}::due")
            new_time = right.time_input(
                "Time", value=_to_time(task.time), step=300, key=f"{k}::time"
            )
            new_duration = left.number_input(
                "Duration (minutes)",
                min_value=1,
                max_value=240,
                value=task.duration_minutes,
                key=f"{k}::dur",
            )
            new_frequency = right.selectbox(
                "Frequency",
                FREQUENCIES,
                index=FREQUENCIES.index(task.frequency.value),
                key=f"{k}::freq",
            )
            save_col, remove_col = st.columns(2)
            save_clicked = save_col.form_submit_button(
                "Save changes", type="primary", icon=":material/save:"
            )
            remove_clicked = remove_col.form_submit_button(
                "Remove task", icon=":material/delete:"
            )

        if save_clicked:
            clean_description = new_description.strip()
            if not clean_description:
                st.error("Description can't be empty.")
            else:
                changes = {
                    "description": clean_description,
                    "task_type": TaskType(new_type),
                    "priority": Priority(new_priority),
                    "due_date": new_due,
                    "time": _hhmm(new_time),
                    "duration_minutes": int(new_duration),
                    "frequency": Frequency(new_frequency),
                }
                try:
                    updated = edit_pet.update_task(task.description, task.time, changes)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    if updated:
                        _flash(f"Updated '{clean_description}' for {edit_pet.name}.", "Schedule")
                    else:
                        st.warning("That task could not be found. It may have been removed.")

        if remove_clicked:
            if edit_pet.remove_task(task.description, task.time):
                _flash(f"Removed '{task.description}' from {edit_pet.name}.", "Schedule")
            else:
                st.warning("That task could not be found. It may already be removed.")

    # --- Today's plan -------------------------------------------------------
    st.divider()
    st.subheader("Today's plan")
    if st.button("Build today's plan", type="primary", icon=":material/calendar_today:"):
        st.session_state["show_plan"] = True

    # Once built, the plan stays open and is recomputed on every run, so it
    # always reflects the latest tasks and sidebar constraints.
    if st.session_state.get("show_plan"):
        scheduler = Scheduler(owner)
        plan = scheduler.build_daily_plan(today)
        skipped = scheduler.skipped_tasks(today)
        explanations = scheduler.explain_plan(today)
        conflicts = scheduler.detect_conflicts(today)

        if not plan and not skipped:
            st.info("Nothing left to do today.")
        else:
            st.markdown("**Planned**")
            if plan:
                st.table(_task_rows(plan, include_pet=True), hide_index=True, alt="Today's plan")
            else:
                st.caption("No tasks fit today's plan.")

            used = sum(t.duration_minutes for t in plan)
            available = owner.available_minutes
            if used <= available:
                st.success(
                    f"{len(plan)} task(s) planned: {used} of {available} min used "
                    f"({available - used} min free)."
                )
            else:
                st.warning(
                    f"{len(plan)} task(s) planned: {used} min, but only {available} min "
                    "available. Medication is always kept, so the plan goes over."
                )

            if skipped:
                st.markdown("**Skipped**")
                st.table(
                    [
                        {
                            "Time": t.time,
                            "Pet": t.pet_name,
                            "Task": t.description,
                            "Minutes": t.duration_minutes,
                            "Priority": t.priority.value,
                            "Reason": _skip_reason(t, explanations),
                        }
                        for t in skipped
                    ],
                    hide_index=True,
                    alt="Tasks skipped today and why",
                )

            st.markdown("**Why each task was planned or skipped**")
            st.markdown("\n".join(f"- {line}" for line in explanations))

        for warning in conflicts:
            st.warning(warning, icon=":material/warning:")


# ===========================================================================
# Health tab
# ===========================================================================

with health_tab:
    _show_flash("Health")
    if not owner.pets:
        st.info("Add a pet in the sidebar to start tracking health.")
    else:
        pet = _pick_pet("Pet", key="health_pet")

        # --- Smart collar ---------------------------------------------------
        st.subheader("Smart collar")
        if pet.collar is None:
            with st.form(f"pair_collar::{pet.name}", clear_on_submit=True):
                left, right = st.columns(2)
                device_id = left.text_input("Device ID", placeholder="e.g. COL-001")
                seed = right.number_input(
                    "Seed",
                    min_value=0,
                    max_value=1_000_000,
                    value=42,
                    step=1,
                    help="The same seed always produces the same simulated readings.",
                )
                st.caption(f"The collar is set up for {pet.name}'s species: {pet.species}.")
                pair_clicked = st.form_submit_button("Pair collar", icon=":material/link:")

            if pair_clicked:
                clean_id = device_id.strip()
                if not clean_id:
                    st.error("Enter the collar's device ID first.")
                else:
                    try:
                        pet.pair_collar(SmartCollar(clean_id, int(seed), species=pet.species))
                    except ValueError as exc:
                        st.error(str(exc))
                    else:
                        _flash(f"Paired collar {clean_id} with {pet.name}.", "Health")
        else:
            st.markdown(
                f"Collar **{pet.collar.device_id}** · battery {pet.collar.battery_percent}%"
            )
            if st.button("Sync now", icon=":material/sync:", key=f"sync::{pet.name}"):
                reading = pet.sync_collar(datetime.now())
                if reading is None:
                    st.warning(f"{pet.name} has no collar paired.")
                else:
                    _flash(
                        f"New reading for {pet.name} at {reading.timestamp:%H:%M:%S}.", "Health"
                    )

        # --- Readings and today's summary -----------------------------------
        st.subheader("Readings")
        readings = sorted(pet.health.readings, key=lambda r: r.timestamp, reverse=True)
        if readings:
            st.table(
                _reading_rows(readings[:MAX_READINGS_SHOWN]),
                hide_index=True,
                alt=f"{pet.name}'s latest collar readings",
            )
            if len(readings) > MAX_READINGS_SHOWN:
                st.caption(f"Showing the latest {MAX_READINGS_SHOWN} of {len(readings)} readings.")
        else:
            st.caption("No readings yet. Pair a collar and press Sync now.")

        st.markdown(f"**Today's summary** ({today:%B %d})")
        st.table(
            _summary_rows(pet.health.daily_summary(today)),
            hide_index=True,
            alt=f"{pet.name}'s health summary for today",
        )

        # --- Alerts ---------------------------------------------------------
        st.subheader("Alerts")
        alerts = pet.health.check_alerts(pet.species)
        for alert in alerts:
            st.warning(alert, icon=":material/monitor_heart:")
        if not alerts:
            if pet.health.latest_reading() is None:
                st.info("No readings yet, so there is nothing to check.")
            elif pet.species not in VITAL_RANGES:
                st.info(f"There are no normal ranges for {pet.species}s, so alerts are off.")
            else:
                st.success("The latest reading is within the normal range.")
        st.caption("Not veterinary advice. Contact your vet if you are worried.")

        # --- Medications ----------------------------------------------------
        st.subheader("Medications")
        if pet.health.medications:
            st.table(
                [
                    {
                        "Name": m.name,
                        "Dose": m.dose,
                        "Times": ", ".join(m.times),
                        "Repeats": m.frequency.value,
                        "Starts": m.start_date.isoformat(),
                    }
                    for m in pet.health.medications
                ],
                hide_index=True,
                alt=f"{pet.name}'s medications",
            )
        with st.form(f"add_med::{pet.name}", clear_on_submit=True):
            left, right = st.columns(2)
            med_name = left.text_input("Medication name", placeholder="e.g. Carprofen")
            dose = right.text_input("Dose", placeholder="e.g. 25 mg")
            times_text = left.text_input(
                "Times", placeholder="08:00, 20:00", help="24-hour HH:MM, separated by commas."
            )
            med_frequency = right.selectbox(
                "Frequency", FREQUENCIES, index=FREQUENCIES.index(Frequency.DAILY.value)
            )
            start_date = left.date_input("Start date", value=today)
            add_med_clicked = st.form_submit_button("Add medication", icon=":material/medication:")

        if add_med_clicked:
            clean_name, clean_dose = med_name.strip(), dose.strip()
            times = _split_csv(times_text)
            if not clean_name or not clean_dose:
                st.error("Enter the medication's name and dose.")
            else:
                try:
                    pet.add_medication(
                        Medication(
                            name=clean_name,
                            dose=clean_dose,
                            times=times,
                            frequency=Frequency(med_frequency),
                            start_date=start_date,
                        )
                    )
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _flash(
                        f"Added {clean_name} for {pet.name}. {len(times)} reminder(s) "
                        "were added to the schedule.",
                        "Health",
                    )

        # --- Symptoms -------------------------------------------------------
        st.subheader("Symptoms")
        if pet.health.symptoms:
            st.table(
                [
                    {
                        "Date": s.logged_on.isoformat(),
                        "Symptom": s.description,
                        "Severity": s.severity.value,
                    }
                    for s in sorted(pet.health.symptoms, key=lambda s: s.logged_on, reverse=True)
                ],
                hide_index=True,
                alt=f"{pet.name}'s symptom log",
            )
        with st.form(f"log_symptom::{pet.name}", clear_on_submit=True):
            symptom = st.text_input("Symptom", placeholder="e.g. Limping on front left leg")
            severity = st.selectbox("Severity", SEVERITIES)
            log_clicked = st.form_submit_button("Log symptom", icon=":material/edit_note:")

        if log_clicked:
            clean_symptom = symptom.strip()
            if not clean_symptom:
                st.error("Describe the symptom first.")
            else:
                pet.health.log_symptom(
                    SymptomEntry(
                        logged_on=today,
                        description=clean_symptom,
                        severity=Severity(severity),
                    )
                )
                _flash(f"Logged '{clean_symptom}' for {pet.name}.", "Health")

        # --- Conditions and allergies ---------------------------------------
        st.subheader("Conditions and allergies")
        with st.form(f"health_lists::{pet.name}"):
            conditions_text = st.text_input(
                "Conditions",
                value=", ".join(pet.health.conditions),
                placeholder="e.g. joint health, sensitive skin",
                help="Comma-separated. Food that supports these ranks higher in the Shop.",
            )
            allergies_text = st.text_input(
                "Allergies",
                value=", ".join(pet.health.allergies),
                placeholder="e.g. chicken, fish",
                help="Comma-separated. Food containing these is never recommended.",
            )
            lists_clicked = st.form_submit_button("Save conditions and allergies")

        if lists_clicked:
            pet.health.conditions = _clean_terms(conditions_text)
            pet.health.allergies = _clean_terms(allergies_text)
            _flash(f"Updated {pet.name}'s conditions and allergies.", "Health")


# ===========================================================================
# Shop tab
# ===========================================================================

with shop_tab:
    _show_flash("Shop")
    st.caption("Simulated store. Fictional brands. No real payment is taken.")
    if not owner.pets:
        st.info("Add a pet in the sidebar to start shopping.")
    else:
        pet = _pick_pet("Shopping for", key="shop_pet")
        market = Marketplace(SAMPLE_CATALOG)
        # recommend_for() only returns safe products, best first; asking for the
        # whole catalog gives every safe product, and the rest are the exclusions.
        safe = market.recommend_for(pet, len(market.catalog))
        safe_ids = {p.product_id for p in safe}
        excluded = [p for p in market.catalog if p.product_id not in safe_ids]
        products_by_id = {p.product_id: p for p in market.catalog}

        # --- Recommendations ------------------------------------------------
        st.subheader(f"Recommended for {pet.name}")
        if not safe:
            st.info(f"This store has no food that is safe for {pet.name}.")
        for rank, product in enumerate(safe[:3], start=1):
            with st.container(border=True):
                st.markdown(
                    f"**{rank}. {product.brand} · {product.name}** · "
                    f"{_money(product.price)} · score {market.score(product, pet):g}"
                )
                st.markdown(
                    "\n".join(
                        f"- {_escape_dollars(line)}"
                        for line in market.explain_recommendation(product, pet)
                    )
                )

        if excluded:
            with st.expander(f"Not recommended for {pet.name} ({len(excluded)})"):
                st.table(
                    [
                        {
                            "Product": f"{p.brand} · {p.name}",
                            "Reason": market.explain_recommendation(p, pet)[0],
                        }
                        for p in excluded
                    ],
                    hide_index=True,
                    alt=f"Products excluded for {pet.name} and why",
                )

        # --- Search ---------------------------------------------------------
        st.subheader("Search")
        query = st.text_input(
            "Search by name or brand", placeholder="e.g. salmon", key="shop_query"
        ).strip()
        if query:
            results = market.search(pet.species, query)
            if results:
                st.table(
                    [
                        {
                            "Product": f"{p.brand} · {p.name}",
                            "Price ($)": f"{p.price:.2f}",
                            "Rating": p.rating,
                            f"Safe for {pet.name}": "✓" if p.product_id in safe_ids else "✗",
                        }
                        for p in results
                    ],
                    hide_index=True,
                    alt="Search results",
                )
            else:
                st.caption(f"No {pet.species} food matches '{query}'.")

        # --- Compare --------------------------------------------------------
        st.subheader("Compare")
        species_ids = [p.product_id for p in market.catalog if p.species == pet.species]
        to_compare = st.multiselect(
            "Products to compare",
            options=species_ids,
            format_func=lambda pid: _product_label(products_by_id[pid]),
            key=f"compare::{pet.species}",
        )
        if to_compare:
            st.table(
                [
                    {
                        "Product": f"{row['brand']} · {row['name']}",
                        "Life stage": row["life_stage"],
                        "Price ($)": f"{row['price']:.2f}",
                        "Rating": row["rating"],
                        "kcal/cup": row["kcal_per_cup"],
                        "Supports": ", ".join(row["supports"]) or "–",
                        "Allergens": ", ".join(row["allergens"]) or "–",
                    }
                    for row in market.compare(to_compare)
                ],
                hide_index=True,
                alt="Product comparison",
            )

        # --- Add to cart ----------------------------------------------------
        st.subheader("Add to cart")
        if safe:
            with st.form(f"add_to_cart::{pet.name}", clear_on_submit=True):
                product_id = st.selectbox(
                    "Product",
                    [p.product_id for p in safe],
                    format_func=lambda pid: _product_label(products_by_id[pid]),
                    help=f"Only food that is safe for {pet.name} is listed.",
                )
                quantity = st.number_input("Quantity", min_value=1, max_value=20, value=1, step=1)
                add_clicked = st.form_submit_button(
                    "Add to cart", icon=":material/add_shopping_cart:"
                )

            if add_clicked:
                product = products_by_id[product_id]
                try:
                    owner.cart.add_item(product, int(quantity))
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _flash(f"Added {int(quantity)} × {product.name} to your cart.", "Shop")
        else:
            st.caption(f"Nothing in this store is safe for {pet.name}.")

        # --- Cart and checkout ----------------------------------------------
        st.subheader("Cart")
        if owner.cart.items:
            st.table(
                [
                    {
                        "Product": f"{item.product.brand} · {item.product.name}",
                        "Qty": item.quantity,
                        "Price ($)": f"{item.product.price:.2f}",
                        "Subtotal ($)": f"{item.subtotal():.2f}",
                    }
                    for item in owner.cart.items
                ],
                hide_index=True,
                alt="Shopping cart",
            )
            st.markdown(f"**Total: {_money(owner.cart.total())}**")

            # The cart is shared across pets, so flag anything unsafe for the pet
            # whose schedule gets the delivery.
            unsafe = [i.product.name for i in owner.cart.items if i.product.product_id not in safe_ids]
            if unsafe:
                st.warning(f"Not safe for {pet.name}: {', '.join(unsafe)}.")

            st.caption(f"The delivery reminder goes on {pet.name}'s schedule.")
            if st.button("Checkout", type="primary", icon=":material/shopping_cart_checkout:"):
                try:
                    order = owner.cart.checkout(owner, MockPayment(), pet.name, today)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    _flash(
                        f"Order {order.order_id} placed ({_money(order.total)}). "
                        f"Delivery on {order.delivery_date:%A, %B %d}; "
                        f"a reminder was added to {pet.name}'s schedule.",
                        "Shop",
                    )
        else:
            st.caption("Your cart is empty.")

        # --- Orders ---------------------------------------------------------
        st.subheader("Orders")
        if owner.orders:
            st.table(
                [
                    {
                        "Order": o.order_id,
                        "Placed": o.placed_on.isoformat(),
                        "Delivery": o.delivery_date.isoformat(),
                        "Items": sum(i.quantity for i in o.items),
                        "Total ($)": f"{o.total:.2f}",
                        "Status": o.status.value,
                    }
                    for o in reversed(owner.orders)
                ],
                hide_index=True,
                alt="Your orders",
            )
        else:
            st.caption("No orders yet.")
