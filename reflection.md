# PawPal+ Project Reflection

## 1. System Design

**a. Initial design**

**Three core actions a user should be able to perform**

1. **Set up my pets and their health information.**
   As an owner, I add each pet with its name, species, breed, age, and weight. For each pet
   I can record its health details: known conditions (for example, joint problems), allergies
   (for example, chicken), medications with the dose and the times they need to be given, and
   any symptoms I notice, rated mild, moderate, or severe. If my pet wears the PawPal+ smart
   collar, I pair it to that pet so its readings sync into the pet's health profile.

2. **Schedule care tasks and tell the app how much time I have.**
   I add the care tasks my pets need: walks, feeding, medication, enrichment, grooming, and
   appointments. Each task has a time, a duration, a priority (low, medium, high), and how
   often it repeats (once, daily, weekly). I also tell the app my limits for the day: how many
   minutes I have for pet care, my waking hours, and which kinds of tasks I want done first
   when I'm short on time.

3. **See today's plan and understand why it looks that way.**
   The app builds my day for me. It only uses tasks inside my waking hours, always keeps
   medication, ranks the rest by priority and my preferred task types, and fills my available
   time. It then explains every decision in plain English, including why a task was skipped
   (for example, "not enough time left: needs 45 min, 20 min left"). It also warns me when two
   tasks are scheduled at the same time, shows health alerts when a collar reading is outside
   the normal range for that species, and automatically creates the next walk or feeding
   when I mark a daily task as done.

**Why I added the Health Tracker and the Food Marketplace**

- **Health Tracker:** People track their own heart rate, sleep, and activity with
  smartwatches, but pets can't tell us when something feels wrong. I wanted a collar or strap,
  worn like a piece of jewelry, that tracks heart rate, oxygen level, temperature, breathing
  rate, sleep score, steps, distance walked, and calories burned. It also keeps medications
  and symptoms in one place, so the owner can spot early warning signs instead of guessing.
  It connects to the scheduler: every medication automatically becomes a reminder task in
  the daily plan.
- **Food Marketplace:** It is hard for pet owners to find good-quality food from well-known,
  trusted sellers, and comparing brands means jumping between many websites. The
  marketplace recommends food that fits each pet's health conditions and never shows food
  containing the pet's allergens. It explains why each product was recommended, lets the
  owner compare brands side by side, and supports add to cart, pay, and doorstep delivery.
  The delivery date also shows up as a task in the schedule. In this version the payment
  is simulated and the brands are fictional.

**How I built the UML**

I built the diagram in rounds, using Claude in two roles:

1. I described my app and my two extra features to Claude in chat, which drafted a first
   class design.
2. I checked it against the starter README and noticed it was missing two of the
   scenario's constraints: time available and owner preferences. I had them added: Owner
   got a time budget, waking hours, and preferred task types, and Scheduler got planning
   methods.
3. I wrote my full brainstorm (every class, attribute, method, and relationship) into a
   prompt for Claude in VS Code, which generated `diagrams/uml.mmd`. I compared it with the
   chat version and checked that it rendered in Mermaid Live.

The final design has 15 classes and 5 enums in three groups: Core Scheduling, Health
Tracker, and Food Marketplace.

**Classes and their responsibilities**

*Core scheduling*

- **Owner**: Holds the owner's info (name, email, address) and daily constraints
  (`available_minutes`, `day_start`, `day_end`, `preferred_types`). Owns the list of pets,
  the shopping cart, and past orders. `get_all_tasks()` is the single place the Scheduler
  gets tasks from, across every pet. Also saves and loads all data as JSON.
- **Pet** (dataclass): One animal's identity and its list of care tasks. Can add, remove,
  and list tasks, and holds the pet's HealthProfile and an optional SmartCollar.
- **Task** (dataclass): One care activity, with a description, time ("HH:MM"), due date,
  type, frequency, priority, duration, and whether it's done. `mark_complete()` returns the
  next occurrence for daily and weekly tasks.
- **Scheduler**: The "brain." It never stores data. It reads tasks through the Owner, then
  sorts them (by time, or by priority then time), filters them (by pet or status), detects
  time conflicts, completes tasks, builds the daily plan within the owner's time, lists
  skipped tasks, and explains every decision.
- **Enums**: `Priority` (low/medium/high), `Frequency` (once/daily/weekly), and `TaskType`
  (walk, feeding, medication, grooming, enrichment, appointment, delivery).

*Health Tracker*

- **SmartCollar**: The simulated wearable. It has a device ID, a battery level, and a seed,
  so the same collar always produces the same readings for testing.
- **HealthReading** (dataclass): One snapshot of vitals: heart rate, SpO2, temperature,
  breathing rate, sleep score, steps, distance, and calories.
- **HealthProfile**: Each pet's health record: conditions, allergies, medications, symptoms,
  and readings. Gives a daily summary and checks readings against normal ranges for dogs and
  cats to raise alerts (shown with a "not veterinary advice" note).
- **Medication** (dataclass): Name, dose, times, and frequency. `to_tasks()` turns it into
  reminder tasks for the scheduler.
- **SymptomEntry** (dataclass) + **Severity** enum: A dated note about a symptom and how
  serious it is.

*Food Marketplace*

- **Marketplace**: Holds the product catalog. Searches it, scores each product for a
  specific pet (wrong species and allergens are excluded first), recommends the top matches,
  explains each recommendation, and compares products side by side.
- **FoodProduct** (dataclass): Brand, name, species, life stage, price, rating, calories per
  cup, the health conditions it supports, and its allergens.
- **Cart** and **CartItem**: What the owner is about to buy, with quantities and a total.
  `checkout()` turns the cart into an order.
- **MockPayment**: A stand-in for real payment. It never asks for or stores card details.
- **Order** (dataclass) + **OrderStatus** enum: A placed order that moves from placed to
  shipped to delivered, and creates a delivery task on its delivery date.

**Key relationships**

- An Owner owns many Pets, and each Pet has many Tasks (composition).
- Each Pet has exactly one HealthProfile and can wear zero or one SmartCollar.
- The Scheduler uses the Owner and only reads tasks through `get_all_tasks()`, so it works
  across all pets instead of just one.
- Medication and Order both create Tasks, which is how the Health Tracker and Marketplace
  feed into the daily plan instead of being separate apps.
- The Marketplace reads a pet's HealthProfile (conditions and allergies) to make safe,
  relevant recommendations.

**b. Design changes**

Yes. The design changed several times before I wrote any real logic. Each change came from
checking AI output against the requirements or against itself.

- **Change 1: Added owner constraints and a real daily planner.** The first draft had Owner
  storing only name, email, address, and pets, and the Scheduler could only sort, filter,
  and detect conflicts. The starter README asks the app to consider "time available,
  priority, owner preferences" and to "explain why it chose that plan." Priority was
  covered, but time and preferences were not, so the Scheduler could only reorder tasks,
  not choose them. I added `available_minutes`, `day_start`, `day_end`, and
  `preferred_types` to Owner, and `build_daily_plan()`, `skipped_tasks()`, and
  `explain_plan(day)` to Scheduler.

- **Change 2: Accepted 7 improvements Claude in VS Code made to the diagram.** When it
  generated `uml.mmd` from my brainstorm, it went beyond what I wrote:
  - `Optional` return types where a method can find nothing (`get_pet`, `latest_reading`, …)
  - a `time` parameter on `remove_task` and `mark_task_complete`, so two tasks with the
    same name ("Feed" at 08:00 and 18:00) can't be confused
  - `HealthProfile` as a dataclass
  - `advance_status()` returning `bool`
  - three missing relationships, including "Order contains CartItems"

  I accepted all 7 because each one made the design more accurate. The Order/CartItem
  change exposed a real bug risk: if checkout passed the cart's own list into the order and
  then cleared the cart, the order would end up empty. The rule is now that checkout copies
  the list (`items=list(self.items)`).

- **Change 3: Fixed task identity after recurrence.** Claude in VS Code said description +
  time uniquely identifies a task. Claude in chat pointed out that's false once a daily
  task repeats: tomorrow's "Walk 08:00" has the same description and time as today's.
  Two rules fix it:
  - `mark_task_complete`, `remove_task`, and `update_task` act on the earliest-due
    *incomplete* match
  - `add_task` rejects exact duplicates (same description, time, and date)

- **Change 4: Applied the skeleton review.** I asked Claude to review `pawpal_system.py`
  for missing relationships and logic bottlenecks. It found 22 issues. The biggest
  changes I made:
  - **Medication reminders never reached the schedule.** `to_tasks()` created them but
    nothing added them to a pet. I added `Pet.add_medication()`, which stores the
    medication *and* adds its reminder tasks.
  - **Tasks couldn't be edited**, but the README requires editing. Changing fields
    directly would skip the time-format and duplicate checks, so I added
    `Pet.update_task()`, which re-validates.
  - **Checkout didn't know which pet a delivery was for, or what day it was.** It now
    takes `pet_name` and `today` and adds the delivery task to that pet.
  - **Medication vs. waking hours conflicted:** a 6 AM pill with a 7 AM day start would
    have been dropped. I decided medication always wins.
  - **The clock is now a parameter.** The collar's readings take a timestamp, and the
    logic layer never reads the system clock, so tests give the same result every run.
  - **CANCELLED order status could never be set.** Claude offered to add a `cancel()`
    method; I removed CANCELLED instead to keep scope small.

- **Change 5: Kept `load_from_json` as a `@classmethod`.** The UML marks it static (`$`)
  because Mermaid has no classmethod symbol. A classmethod is the standard Python way to
  build an object from a file, so I kept it and added a comment in the diagram.

- **Change 6:** [FILL IN after Phase 6: the differences between the final code and the
  diagram, and what you updated.]

---

## 2. Scheduling Logic and Tradeoffs

---

**a. Constraints and priorities**

My scheduler considers these constraints, in this order:

1. **Medication always stays in the plan**, even outside the owner's waking hours or over
   the time budget. Its minutes still count toward the total. Health comes first.
2. **The owner's waking hours** (`day_start` to `day_end`, default 07:00–21:00). Any other
   task outside these hours is skipped, because the owner can't do it.
3. **Priority** (high, then medium, then low): the owner's own rating of how much a
   task matters.
4. **Preferred task types.** When two tasks have the same priority, the one the owner
   prefers (for example, walks) goes first.
5. **Time of day** breaks any remaining ties, and the final plan is shown in time order.
6. **Available minutes** (default 120). The planner goes down the ranked list and adds
   each task that fits. If one doesn't fit, it skips it and keeps trying smaller ones.

The Food Marketplace has its own hard rules: food for the wrong species, or food that
contains one of the pet's allergens, is never recommended, no matter how well it scores.

**How I decided which constraints mattered most:** I split them into hard rules and soft
preferences. Hard rules protect the pet or reflect real limits: medication, allergens,
and the owner's actual hours and time. When two hard rules conflicted (a 6 AM pill vs. a
7 AM day start), I chose medication, because a missed dose can hurt the pet and a slightly
early task can't. Soft preferences come after: priority first, because the owner chose it
on purpose, then preferred types, then time of day. Keeping safety rules separate from
scoring also makes every decision easy to explain.

---

**b. Tradeoffs**

- **Conflict detection only checks exact time matches.** Two tasks are flagged only if
  they share the same date and the same "HH:MM" time. A 30-minute walk at 08:00 and a
  feeding at 08:15 overlap, but they aren't flagged. This is reasonable for now because
  most owners schedule pet care at round times, some tasks can be done together, and an
  exact-match check is simple to read and easy to test. Checking overlapping durations
  would need start and end times plus interval logic. That's my first planned improvement.
- **The planner is greedy, not optimal.** It takes tasks in ranked order, adds each one
  that fits, and skips any that don't while still trying smaller ones. That doesn't always
  get the best possible combination of tasks. I chose it because the owner can predict it
  ("high priority first, then what you prefer"), and every decision can be explained in
  one sentence. For an app that has to explain itself, a predictable rule is worth more
  than squeezing in one extra task.
- **Recurring tasks only roll forward when completed.** Tomorrow's walk is created when
  today's walk is marked done. If the owner skips a day, the walk doesn't appear on later
  days until they complete the old one. That keeps recurrence simple and avoids flooding
  the schedule with copies, but it means a forgotten task can quietly drop off the plan.
  Generating upcoming occurrences ahead of time is a future improvement.
- **Preference can push out a meal.** Preferred task types break ties within the same
  priority. With 60 minutes and two preferred HIGH walks, a HIGH breakfast gets skipped.
  That follows my rules, but a pet could miss a meal because the owner prefers walks. I
  kept it because the explanation makes the tradeoff visible ("Not enough time left"),
  and the owner can raise their minutes or change preferences. Treating feeding like
  medication is a possible future rule.

---

## 3. AI Collaboration

**a. How you used AI**

I used Claude in two roles:

- **Claude in chat, as my planning partner.** It read the project brief and grading
  rubric and helped me build a phase-by-phase plan where every step maps to rubric points. It drafted the detailed UML from my feature ideas (Health Tracker and Food Marketplace), rendered the diagram to check it was readable, and wrote `CLAUDE.md`, the rules file that Claude in VS Code reads at the start of every session. It also reviewed my design when I spotted missing requirements.
- **Claude in VS Code, as my builder.** It generated `diagrams/uml.mmd` from my full
  brainstorm, adding 7 improvements I accepted. It wrote the class skeleton, built a script to compare the code against the UML, and reviewed the skeleton (22 findings).
  In Phase 2 it implemented Task, Pet, Owner, and `Scheduler.get_todays_schedule()`, wrote `main.py` with an aligned schedule table, wrote the first two tests, and drafted the README summary. [ADD as you go: Phase 3 UI, Phase 4 algorithms, Phase 5 tests.]

**What helped most:**

- `CLAUDE.md` as context engineering. My design rules (for example, "the Scheduler only
  reads tasks through `owner.get_all_tasks()`") carried over into every session, even
  after `/clear`, so I didn't have to repeat them.
- Asking for a plan before any edit ("Show me your plan before editing") and using plan
  mode, so I could catch problems before code was written.
- "Compare @pawpal_system.py against @diagrams/uml.mmd and list every difference." This
  kept the code and the diagram matched.
- Giving exact rules and example outputs, like the explain_plan sentences, instead of
  vague requests.
- A separate session per phase. [FILL IN: one concrete way this helped, e.g., the
  testing session wasn't confused by earlier algorithm discussions.]

---

**b. Judgment and verification**

- **Moment 1 (already happened):** Claude's first UML draft looked complete, but when I
  compared it with the starter README, it was missing two of the three constraints the
  scenario asks for: time available and owner preferences. I didn't accept the draft as
  it was. I asked for those to be added, and the design got a real daily planner instead
  of just sorting.
- **Moment 2:** When Claude in VS Code generated the UML, it said description + time
  uniquely identifies a task. Claude in chat pointed out that's false once a daily task
  repeats: tomorrow's "Walk 08:00" has the same description and time as today's. I didn't
  accept the claim as stated. I added two rules to CLAUDE.md: actions target the
  earliest-due *incomplete* match, and exact duplicates (same description, time, and
  date) are rejected.
- **Moment 3:** Claude's README summary was accurate but was one dense paragraph, and it
  implied the owner's time limits already shaped the schedule, which they won't until
  Phase 4. I split it into one bullet per class and added a line saying the limits drive
  the upcoming planner, so the README doesn't promise behavior `main.py` can't show yet.
- **Moment 4: Algorithm brainstorm.** Claude suggested 7 improvements. I accepted 2: a
  priority rank table, because sorting the text "high/low/medium" alphabetically puts LOW
  before MEDIUM (a real bug), and an end-time check, because a 20:45 task lasting 20 min
  ends after my 21:00 day end. I rejected 5 as out of scope or as changes to documented
  tradeoffs (overlap detection, slot suggestions, shortest-first, catch-up recurrence,
  combined dog walks).
- **Moment 5: Model comparison caught a rule violation.** Comparing Claude and Gemini on
  recurring tasks showed that Claude's `mark_task_complete` read `pet.tasks` directly,
  breaking my "Scheduler only reads through Owner" rule, while Gemini's version followed
  it. I had Claude rewrite it, and Claude in chat confirmed the Scheduler no longer
  touches `pet.tasks` (details in `ai_interactions.md`).
- **Moment 6: Explanations that hide the important case.** Claude's planner gave every
  medication the same reason. I changed it so the explanation says when the medication
  rule overrode the owner's hours or time budget, because those are exactly the moments
  an owner needs to understand.

**How I verified AI output:**

- **Ran the code:** I ran `python main.py` and checked the schedule by eye (right
  pets, right order), and ran `python -m pytest` (2 passed).
- **Cross-checked UML against code twice:** once with Claude in VS Code's script and
  once independently with Claude in chat. Both found 20 classes and enums and 46
  matching methods. Claude in VS Code's first run reported 41 "type mismatches" that
  turned out to be a bug in its own checker, which is a reminder that the checking
  tool needs checking too.
- Claude in chat ran 13 edge-case checks on the planner (medication outside hours and
  over budget, skip-then-fit, budget never exceeded, MEDIUM before LOW, preference
  tie-break across pets, day-end boundaries, recurrence chain, no duplicate next
  occurrence). All passed.
- **Tested the rules directly:** I had Claude in chat run 20 checks on the
  `CLAUDE.md` rules (bad times, duplicate pets and tasks, editing the earliest
  incomplete task). All passed.
- **Checked the diagram rendered,** in Mermaid Live and on GitHub.

---

## 4. Testing and Verification

**a. What you tested**

[FILL IN after Phase 5. Keep only the tests you actually wrote and that pass.]

- **Core:** marking a task complete; adding a task increases the pet's task count;
  invalid times like "9:00" are rejected.
- **Scheduling:** sorting by time; sorting by priority then time; filtering by pet;
  daily tasks recur the next day; one-time tasks don't recur; conflicts are flagged
  across two pets; a pet with no tasks gives an empty schedule.
- **Daily plan:**
  - never goes over the owner's available minutes (medication aside)
  - when time is tight, high priority beats low
  - preferred types win ties
  - medication is always kept
  - tasks outside waking hours are skipped
  - skipped tasks explain why
- **Health:** high heart rate triggers an alert; normal readings don't; medication creates
  one reminder per time; the same seed gives the same reading.
- **Marketplace:** allergen and wrong-species products are never recommended;
  explanations mention the matched condition; cart totals are correct; empty-cart
  checkout raises an error; checkout creates a delivery task.
- **Save/load:** saving and loading gives back the same pets, tasks, enum values, and
  dates.

**Why these tests matter:** [FILL IN in your words. Starting point: they cover the
behaviors where a silent bug would hurt the owner most. A skipped medication, an allergen
in a recommendation, or a plan that ignores the owner's time would all look fine on screen
but be wrong.]

**b. Confidence**

[FILL IN: X/5 stars.] All [N] tests pass. [FILL IN: one sentence on why that number,
e.g., "Core scheduling is well covered, but the UI is only tested by hand."]

**Edge cases I'd test next:**

- Tasks with overlapping durations, not just the exact same time.
- Two tasks on the same pet with the same description. `mark_task_complete` finds tasks
  by description, so it could complete the wrong one. Task IDs would fix this.
- A task near midnight whose next occurrence crosses into the next day or month.
- An owner with 0 available minutes, or waking hours where `day_end` is before
  `day_start`.
- Loading a damaged or hand-edited `data.json`.
- Health readings for species other than dog and cat (tracked, but no alerts).

---

## 5. Reflection


**a. What went well**

[FILL IN in Phase 6. Ask yourself: what part would you show in an interview? Likely
candidates: the explainable daily plan (it tells the owner why something was skipped),
the allergen-safe recommendations with reasons, or CLAUDE.md keeping the AI consistent
across sessions.]

**b. What you would improve**

[FILL IN in Phase 6. Candidates based on the current design:

- overlap-based conflict detection using durations
- unique task IDs instead of matching by description
- connecting a real wearable instead of simulated readings
- a smarter planner that suggests moving a skipped task to a free time slot instead of
  just dropping it
- a real payment provider and real product data for the marketplace]

**c. Key takeaway**

[FILL IN in your words. One starting point that's already true: the AI was fast and
thorough at building what I described, but it only covered what I asked for. When the
design missed the README's constraints, the draft missed them too. Being the lead
architect meant checking the spec against the real requirements, not just checking
whether the code ran.]
