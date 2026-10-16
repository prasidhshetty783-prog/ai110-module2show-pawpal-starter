# AI Interactions Log

> **Stretch features only.** Only fill in the sections that apply to stretch features you attempted. If you did not attempt a stretch feature, leave its section blank or delete it. This file is not required for the core project.

---

## Agent Workflow (SF7)

> Document your experience using an AI agent (e.g., Cursor Agent, Claude, Copilot) to make multi-step changes autonomously.

**What task did you give the agent?**

<!-- Describe the goal you asked the agent to accomplish -->

**What did the agent do?**

<!-- List the steps the agent took (files edited, commands run, etc.) -->

**What did you have to verify or fix manually?**

<!-- Describe anything the agent got wrong or that required human review -->

---

## Prompt Comparison (SF11)

> Compare two different prompts (or two different models) on the same task.

**Task:** implement recurring tasks: `Task.next_occurrence()`, `Task.mark_complete()`, and
`Scheduler.mark_task_complete(pet_name, description, time)`.

| | Option A | Option B |
|-|----------|----------|
| **Model / tool used** | Claude (Claude Code in VS Code) | Gemini 3.8 Flash (gemini.google.com web app) |
| **Prompt** | My recurrence prompt (DAILY +1 day, WEEKLY +7 days, earliest-due incomplete match, return the existing next occurrence instead of duplicating, never raise), run inside my project with `CLAUDE.md` loaded. | The same rules, plus the context Claude had from `CLAUDE.md` (duplicate rule, `get_all_tasks()` rule, no `date.today()`), and my `Task` and `Scheduler` classes with empty method bodies, so it couldn't copy Claude's finished answer. |
| **Response summary** | Edited `pawpal_system.py` in place. A `_RECURRENCE_STEP` lookup table maps DAILY/WEEKLY to a `timedelta`; `dataclasses.replace` copies the task with the new date and `completed=False`. `mark_task_complete` checks whether tomorrow's copy already exists before adding it. | Returned one complete `main.py`. An if/elif chain picks the `timedelta`; also uses `dataclasses.replace`. `mark_task_complete` finds the match through `owner.get_all_tasks()`, catches the duplicate `ValueError`, and wraps the whole method in `try/except Exception`. Its demo output was accurate when I ran it. |
| **What was useful** | Clean lookup table instead of if/elif. Copies every field automatically. Explicit `None` returns for each "nothing to do" case. Kept my existing validation and enums untouched. | **Followed my architecture rule:** the Scheduler reads tasks only through `owner.get_all_tasks()`. Correctly completes the earliest-due incomplete task (I tested a second completion after rollover; it finished tomorrow's task, not today's). |
| **Problems noticed** | **Broke my own rule:** `mark_task_complete` read `pet.tasks` directly and called Pet's private `_find_task()`, even though `CLAUDE.md` says the Scheduler may only use `owner.get_all_tasks()`. | Rewrote the whole module into `main.py` and changed things I didn't ask for: replaced my `TaskType` members (added VET/TRAINING/OTHER, dropped ENRICHMENT/APPOINTMENT/DELIVERY), dropped time validation (`"9:00"` was accepted), and defaulted `priority` to `None`. Redundant string checks (`== "daily"`) on an enum that is never a string. The blanket `except Exception: return None` hides real bugs: a broken owner object silently returned `None`. |
| **Decision** | **Kept Claude's structure**: lookup table, `dataclasses.replace`, explicit `None` returns, my enums and validation unchanged. | **Adopted Gemini's approach for finding tasks**: `mark_task_complete` now searches `owner.get_all_tasks()` instead of reaching into `pet.tasks`. Rejected the blanket `try/except` and the rewritten classes. |

**Which approach did you use in your final implementation and why?**

A combination of both. Claude's version was cleaner and respected my existing code, so I
kept its structure. Comparing it against Gemini showed me that Claude had broken my own
"Scheduler only reads through Owner" rule, and Gemini hadn't, so I had Claude rewrite
`mark_task_complete` to search `owner.get_all_tasks()` and checked the other Scheduler
methods for the same problem. I didn't take Gemini's code directly because it rewrote my
enums, removed time validation, and hid errors behind a catch-all `except`.

To check both answers, I ran Gemini's code (with Claude in chat), confirmed its demo
output was real, and tested edge cases on each version: completing a task twice after
rollover, an invalid `"9:00"` time, and a broken owner object.

The main lesson: a second model is most useful as a reviewer. Neither answer was simply
"better", but comparing them exposed a rule violation I would have missed by reading
Claude's code alone.

<!-- Your conclusion -->
