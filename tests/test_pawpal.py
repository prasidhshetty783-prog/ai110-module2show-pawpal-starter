"""Tests for the PawPal+ logic layer."""

from datetime import date

from pawpal_system import Pet, Task, TaskType

DAY = date(2026, 10, 15)


def test_mark_complete_sets_completed_true() -> None:
    """mark_complete() flips a new task from not done to done."""
    task = Task("Morning walk", "07:30", DAY, TaskType.WALK)
    assert task.completed is False

    task.mark_complete()

    assert task.completed is True


def test_add_task_increases_task_count_by_one() -> None:
    """add_task() adds exactly one task to the pet."""
    pet = Pet("Mochi", "dog", "Shiba Inu", age_years=3, weight_kg=10.5)
    before = len(pet.get_tasks())

    pet.add_task(Task("Breakfast", "08:00", DAY, TaskType.FEEDING))

    assert len(pet.get_tasks()) == before + 1
