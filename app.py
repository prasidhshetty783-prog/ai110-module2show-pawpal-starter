"""PawPal+ Streamlit UI. All logic lives in pawpal_system.py; this file only displays it."""

from __future__ import annotations

from datetime import date, datetime, time as dt_time
from pathlib import Path

import streamlit as st

from pawpal_system import Frequency, Owner, Pet, Priority, Scheduler, Task, TaskType

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
SPECIES = ["dog", "cat", "other"]
DATA_FILE = "data.json"

if "owner" not in st.session_state:
    loaded_owner = None
    if Path(DATA_FILE).exists():
        try:
            loaded_owner = Owner.load_from_json(DATA_FILE)
        except (ValueError, KeyError, TypeError) as exc:  # corrupt or hand-edited file
            st.session_state["_flash"] = (
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


def _flash(message: str, kind: str = "success") -> None:
    """Remember a message for the next run, then rerun so every section shows fresh data."""
    st.session_state["_flash"] = (kind, message)
    st.rerun()


def _show_flash() -> None:
    """Show (once) the message saved by _flash, if any."""
    flash = st.session_state.pop("_flash", None)
    if flash is not None:
        kind, message = flash
        getattr(st, kind)(message)


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
# Main page
# ---------------------------------------------------------------------------

st.title("🐾 PawPal+")
st.caption(f"Pet care planner for {owner.name or 'you'} · {today:%A, %B %d, %Y}")
_show_flash()

# --- Add a task -------------------------------------------------------------
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
        duration = left.number_input("Duration (minutes)", min_value=1, max_value=240, value=15)
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
                _flash(f"Added '{clean_description}' for {pet.name}.")

# --- Task list --------------------------------------------------------------
st.divider()
st.subheader("Tasks")
if not owner.pets:
    st.caption("No pets yet.")
for pet in owner.pets:
    st.markdown(f"**{pet.name}** · {pet.species}, {pet.breed or 'breed not set'}")
    pet_tasks = sorted(pet.get_tasks(), key=lambda t: (t.due_date, t.time))
    if pet_tasks:
        st.table(_task_rows(pet_tasks, include_pet=False), hide_index=True, alt=f"{pet.name}'s tasks")
    else:
        st.caption("No tasks yet.")

# --- Edit or remove a task --------------------------------------------------
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
        new_description = st.text_input("Description", value=task.description, key=f"{k}::desc")
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
            "Priority", PRIORITIES, index=PRIORITIES.index(task.priority.value), key=f"{k}::prio"
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
        remove_clicked = remove_col.form_submit_button("Remove task", icon=":material/delete:")

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
                    _flash(f"Updated '{clean_description}' for {edit_pet.name}.")
                else:
                    st.warning("That task could not be found. It may have been removed.")

    if remove_clicked:
        if edit_pet.remove_task(task.description, task.time):
            _flash(f"Removed '{task.description}' from {edit_pet.name}.")
        else:
            st.warning("That task could not be found. It may already be removed.")

# --- Today's schedule -------------------------------------------------------
st.divider()
st.subheader("Today's schedule")
if st.button("Generate schedule", type="primary", icon=":material/calendar_today:"):
    st.session_state["show_schedule"] = True

if st.session_state.get("show_schedule"):
    schedule = Scheduler(owner).get_todays_schedule(today)
    if schedule:
        total = sum(t.duration_minutes for t in schedule)
        st.table(_task_rows(schedule, include_pet=True), hide_index=True, alt="Today's schedule")
        st.success(
            f"{len(schedule)} task(s) today, {total} min in total "
            f"({owner.available_minutes} min available)."
        )
    else:
        st.info("Nothing is due today.")
