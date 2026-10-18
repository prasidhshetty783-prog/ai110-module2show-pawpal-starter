"""PawPal+ Streamlit UI. All logic lives in pawpal_system.py; this file only displays it."""

from __future__ import annotations

import html
from datetime import date, datetime, time as dt_time
from pathlib import Path
from urllib.parse import quote

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
    OrderStatus,
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

st.set_page_config(page_title="PawPal+", page_icon=":material/pets:", layout="centered")

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


# ---------------------------------------------------------------------------
# Look and feel: one style block, line icons, and the pet drawings
# ---------------------------------------------------------------------------

# Colors are the same tokens as .streamlit/config.toml; color only carries meaning.
_CSS = """
:root {
  --pp-bg: #0B0C0E;
  --pp-surface: #15171A;
  --pp-border: #24272B;
  --pp-border-hi: #3A3F45;
  --pp-text: #F2F3F5;
  --pp-muted: #8B9096;
  --pp-line: #C9CDD2;
  --pp-fill: #1E2125;
  --pp-green: #34D399;
  --pp-amber: #F5B841;
  --pp-red: #F87171;
  --pp-radius: 12px;
}

[data-testid="stMainBlockContainer"] { padding-top: 3.5rem; padding-bottom: 6rem; }

/* Buttons: primary is light with a dark label, tertiary is quiet text. */
[data-testid^="stBaseButton-primary"],
[data-testid^="stBaseButton-primary"] p { color: var(--pp-bg) !important; }
/* Anything else Streamlit fills with the light primary color gets dark text too. */
[data-testid="stMultiSelectTagsContainer"] > span > span {
  background: var(--pp-border) !important; border: 1px solid var(--pp-border-hi);
}
[data-testid="stMultiSelectTagsContainer"] > span > span * { color: var(--pp-text) !important; }
[data-testid="stBaseButton-tertiary"] { color: var(--pp-muted); }
[data-testid="stBaseButton-tertiary"]:hover { color: var(--pp-text); }

/* Tabs: muted labels with a thin underline on the open tab. */
[data-testid="stTabs"] [role="tablist"] { gap: 28px; margin-bottom: 8px; }
[data-testid="stTab"] { color: var(--pp-muted); transition: color 200ms ease-out; }
[data-testid="stTab"] p { font-size: 15px; font-weight: 500; color: inherit !important; }
[data-testid="stTab"]:hover,
[data-testid="stTab"][aria-selected="true"] { color: var(--pp-text); }

/* Expanders hold the forms, so they sit quietly on the surface color. */
[data-testid="stExpander"] details {
  background: var(--pp-surface); border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
}
[data-testid="stExpander"] summary p { font-weight: 500; }

/* Header and summary */
.pp-head { margin-bottom: 8px; }
.pp-h1 {
  margin: 0; font-size: 36px; font-weight: 600; line-height: 1.1;
  letter-spacing: -0.02em; color: var(--pp-text);
}
.pp-date { margin: 8px 0 0; font-size: 15px; color: var(--pp-muted); }
.pp-summary {
  display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between;
  gap: 16px; margin-top: 32px; padding: 24px;
  background: var(--pp-surface); border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
}
.pp-big {
  font-size: 40px; font-weight: 600; line-height: 1; letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums; color: var(--pp-text);
}
.pp-big .pp-of { font-size: 20px; font-weight: 500; color: var(--pp-muted); }
.pp-big.warn .pp-used { color: var(--pp-amber); }
.pp-sum-sub { margin-top: 10px; font-size: 14px; color: var(--pp-muted); }
.pp-chip {
  display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px;
  font-size: 13px; font-weight: 500; color: var(--pp-text);
  background: var(--pp-bg); border: 1px solid var(--pp-border); border-radius: 999px;
}

/* Status dots: green planned/healthy, amber attention, red error, ring = neutral. */
.pp-dot {
  display: inline-block; flex: none; width: 8px; height: 8px; border-radius: 50%;
  box-sizing: border-box; border: 1.5px solid var(--pp-muted);
}
.pp-dot.ok { background: var(--pp-green); border: 0; box-shadow: 0 0 0 3px rgba(52, 211, 153, .14); }
.pp-dot.warn { background: var(--pp-amber); border: 0; box-shadow: 0 0 0 3px rgba(245, 184, 65, .14); }
.pp-dot.err { background: var(--pp-red); border: 0; box-shadow: 0 0 0 3px rgba(248, 113, 113, .14); }
.pp-sr {
  position: absolute; width: 1px; height: 1px; overflow: hidden;
  clip: rect(0 0 0 0); white-space: nowrap;
}

/* Pet gallery */
.pp-gallery {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 16px; margin: 8px 0 24px;
}
.pp-card {
  padding: 16px 16px 18px; outline: none;
  background: var(--pp-surface); border: 1px solid var(--pp-border); border-radius: var(--pp-radius);
  transition: transform 200ms ease-out, border-color 200ms ease-out, box-shadow 200ms ease-out;
}
.pp-card:hover, .pp-card:focus-visible {
  transform: translateY(-4px); border-color: var(--pp-border-hi);
  box-shadow: 0 14px 32px -16px rgba(0, 0, 0, .7), 0 0 28px rgba(242, 243, 245, .06);
}
.pp-card:focus-visible { border-color: var(--pp-text); }
.pp-card.is-new { animation: pp-enter 520ms cubic-bezier(.2, .7, .2, 1) backwards; }
/* The drawing box has the SVG's exact 140:100 shape, so each layer lines up and
   transform-origin percentages land on the right joint. */
.pp-art { position: relative; width: 134px; height: 96px; margin: 0 auto; }
.pp-art span { position: absolute; inset: 0; background: center / 100% 100% no-repeat; }
.pp-name {
  margin-top: 12px; font-size: 16px; font-weight: 600; color: var(--pp-text);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.pp-meta { margin-top: 2px; font-size: 13px; color: var(--pp-muted); }

/* Each species has its own move while hovered or keyboard-focused. */
.pp-dog:is(:hover, :focus-visible) .tail { animation: pp-wag 600ms ease-in-out infinite; }
.pp-dog:is(:hover, :focus-visible) .head { animation: pp-tilt 600ms ease-in-out infinite; }
.pp-cat:is(:hover, :focus-visible) .tail { animation: pp-swish 600ms ease-in-out infinite; }
.pp-cat:is(:hover, :focus-visible) .ear { animation: pp-twitch 600ms ease-in-out infinite; }
.pp-other:is(:hover, :focus-visible) .hop { animation: pp-hop 600ms ease-out infinite; }
.pp-other:is(:hover, :focus-visible) .eye { animation: pp-blink 600ms ease-in-out infinite; }
.pp-other:is(:hover, :focus-visible) .shadow { animation: pp-shadow 600ms ease-out infinite; }

@keyframes pp-enter { from { opacity: 0; transform: translateY(14px); } }
@keyframes pp-wag {
  0%, 100% { transform: rotate(0deg); } 25% { transform: rotate(-22deg); } 75% { transform: rotate(14deg); }
}
@keyframes pp-tilt { 0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(-9deg); } }
@keyframes pp-swish { 0%, 100% { transform: rotate(0deg); } 50% { transform: rotate(-16deg); } }
@keyframes pp-twitch {
  0%, 55%, 100% { transform: rotate(0deg); } 70% { transform: rotate(-14deg); } 85% { transform: rotate(6deg); }
}
@keyframes pp-hop { 0%, 100% { transform: translateY(0); } 45% { transform: translateY(-7px); } }
@keyframes pp-blink { 0%, 35%, 65%, 100% { transform: scaleY(1); } 50% { transform: scaleY(.1); } }
@keyframes pp-shadow {
  0%, 100% { transform: scaleX(1); opacity: .45; } 45% { transform: scaleX(.7); opacity: .25; }
}

/* List rows */
.pp-list {
  background: var(--pp-surface); border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius); overflow: hidden;
}
.pp-row { display: flex; align-items: center; gap: 14px; min-height: 56px; padding: 12px 16px; }
.pp-list .pp-row + .pp-row { border-top: 1px solid var(--pp-border); }
.pp-ico {
  display: grid; place-items: center; flex: none; width: 36px; height: 36px;
  color: var(--pp-text); background: var(--pp-bg); border: 1px solid var(--pp-border); border-radius: 10px;
}
.pp-i {
  display: block; width: 18px; height: 18px; background: currentColor;
  -webkit-mask: var(--pp-icon) center / contain no-repeat; mask: var(--pp-icon) center / contain no-repeat;
}
.pp-txt { flex: 1; min-width: 0; }
.pp-title { font-size: 15px; font-weight: 500; line-height: 1.35; color: var(--pp-text); overflow-wrap: anywhere; }
.pp-sub { margin-top: 2px; font-size: 13px; line-height: 1.45; color: var(--pp-muted); overflow-wrap: anywhere; }
.pp-right {
  display: flex; align-items: center; gap: 10px; flex: none;
  font-size: 13px; color: var(--pp-muted); font-variant-numeric: tabular-nums;
}
.pp-right .pp-i { width: 16px; height: 16px; color: var(--pp-muted); }
.pp-label { margin: 16px 0 8px; font-size: 13px; font-weight: 500; color: var(--pp-muted); }
.pp-label b { font-weight: 600; color: var(--pp-text); }
.pp-empty { margin: 0; font-size: 14px; color: var(--pp-muted); }
.pp-explain { margin: 0; padding: 16px 20px 16px 36px; font-size: 14px; line-height: 1.6; color: var(--pp-muted); }

/* Rows that carry a button are Streamlit containers styled to match .pp-list. */
[class*="st-key-pp-alist"] {
  gap: 0; background: var(--pp-surface); border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius); overflow: hidden;
}
[class*="st-key-pp-arow"] { padding-right: 12px; }
[class*="st-key-pp-alist"] > div + div { border-top: 1px solid var(--pp-border); }

/* Health summary stats */
.pp-stats {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap: 4px 0;
  padding: 8px 0; background: var(--pp-surface); border: 1px solid var(--pp-border);
  border-radius: var(--pp-radius);
}
.pp-stat { padding: 10px 16px; }
.pp-stat-v { font-size: 18px; font-weight: 600; color: var(--pp-text); font-variant-numeric: tabular-nums; }
.pp-stat-l { margin-top: 2px; font-size: 12px; color: var(--pp-muted); }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important; animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important; scroll-behavior: auto !important;
  }
  .pp-card, .pp-card * { animation: none !important; }
  .pp-card:hover, .pp-card:focus-visible { transform: none; }
}
"""

# Line icons on a 24 x 24 grid, drawn with currentColor.
_ICONS: dict[str, str] = {
    "walk": '<circle cx="6" cy="18" r="2"/><circle cx="18" cy="6" r="2"/>'
    '<path d="M8 18h7a3 3 0 0 0 0-6H9a3 3 0 0 1 0-6h7"/>',
    "feeding": '<path d="M3 11h18"/><path d="M4 11a8 8 0 0 0 16 0"/><path d="M9 20h6"/>'
    '<path d="M9 7.5c0-1.2.8-1.6.8-2.8M14 7.5c0-1.2.8-1.6.8-2.8"/>',
    "medication": '<path d="M10.5 3.5a4.95 4.95 0 0 1 7 7l-7 7a4.95 4.95 0 0 1-7-7z"/>'
    '<path d="M7 7l7 7"/>',
    "enrichment": '<circle cx="12" cy="12" r="8"/><path d="M5.5 7.5c3 3 3 6 0 9M18.5 7.5c-3 3-3 6 0 9"/>',
    "grooming": '<path d="M4 8h16v4H4z"/><path d="M6 12v6M9 12v6M12 12v6M15 12v6M18 12v6"/>',
    "appointment": '<rect x="4" y="5" width="16" height="15" rx="2"/><path d="M4 10h16M8 3v4M16 3v4"/>',
    "delivery": '<path d="M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z"/><path d="M3 7.5 12 12l9-4.5M12 12v9"/>',
    "collar": '<path d="M5 13a7 7 0 0 1 14 0"/><path d="M8.5 13a3.5 3.5 0 0 1 7 0"/>'
    '<circle cx="12" cy="17" r="1.5"/>',
    "heart": '<path d="M12 20s-7-4.4-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.6-7 10-7 10z"/>'
    '<path d="M8 12h2l1-2 2 4 1-2h2"/>',
    "note": '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 13h6M9 17h4"/>',
    "shield": '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/>',
    "food": '<path d="M6 8h12l-1 13H7z"/><path d="M9 8a3 3 0 0 1 6 0"/>',
    "cart": '<path d="M3 4h2.5l2 11.5h10.5l2-8H7"/><circle cx="9" cy="19.5" r="1"/>'
    '<circle cx="17" cy="19.5" r="1"/>',
}
_ICONS["chevron"] = '<path d="M9 6l6 6-6 6"/>'
_TYPE_ICON: dict[TaskType, str] = {t: t.value for t in TaskType}


def _svg_url(body: str, attrs: str = "") -> str:
    """Return an SVG as a CSS url(): st.html's sanitizer removes inline <svg>, CSS keeps it."""
    view_box = "0 0 24 24" if attrs else "0 0 140 100"
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{view_box}" {attrs}>{body}</svg>'
    return f'url("data:image/svg+xml,{quote(svg)}")'


# Icons are CSS masks filled with currentColor, so they take the text color.
_ICON_STROKE = (
    'fill="none" stroke="#000" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'
)
_ICON_CSS = "".join(
    f".pp-i-{name} {{ --pp-icon: {_svg_url(body, _ICON_STROKE)}; }}\n"
    for name, body in _ICONS.items()
)

# Original line drawings on a 140 x 100 grid. Each moving part (tail, head, ear,
# eyes) is its own full-size layer, so CSS can rotate it around its joint.
_LN = 'fill="none" stroke="#C9CDD2" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"'
_THIN = 'fill="none" stroke="#C9CDD2" stroke-width="1.2" stroke-linecap="round" opacity=".7"'
_FL = 'fill="#1E2125" stroke="#C9CDD2" stroke-width="2" stroke-linejoin="round"'
_INK = 'fill="#F2F3F5"'
_SHADOW = 'fill="#000" opacity=".45"'

# (species, layer class) -> (SVG body, transform-origin at that part's joint).
_PET_PARTS: dict[tuple[str, str], tuple[str, str]] = {
    ("dog", "tail"): (f'<path {_LN} d="M101 55 C110 50 114 42 113 32"/>', "72.1% 55%"),
    ("dog", "base"): (
        f'<ellipse {_SHADOW} cx="72" cy="94" rx="38" ry="3.5"/>'
        f'<path {_LN} d="M52 74 V90 M62 76 V90 M86 76 V90 M96 73 V90"/>'
        f'<ellipse {_FL} cx="74" cy="60" rx="30" ry="17"/>',
        "50% 50%",
    ),
    ("dog", "head"): (
        f'<path {_FL} d="M52 30 C61 30 63 43 58 51 C54 46 51 40 52 30 Z"/>'
        f'<circle {_FL} cx="46" cy="42" r="15"/>'
        f'<ellipse {_FL} cx="32" cy="48" rx="10" ry="7"/>'
        f'<circle {_INK} cx="23.5" cy="46" r="2.6"/>'
        f'<circle {_INK} cx="42" cy="38" r="2"/>'
        f'<path {_THIN} d="M28 53 Q32 55.5 36 53"/>',
        "39.3% 52%",
    ),
    ("cat", "tail"): (
        f'<path {_LN} d="M86 88 C104 88 110 76 104 64 C101 58 96 58 95 62"/>', "61.4% 88%"
    ),
    ("cat", "base"): (
        f'<ellipse {_SHADOW} cx="70" cy="94" rx="30" ry="3.5"/>'
        f'<path {_FL} d="M52 90 C48 72 54 58 70 56 C86 58 92 72 88 90 Z"/>'
        f'<path {_THIN} d="M63 90 V80 M77 90 V80"/>'
        f'<path {_FL} d="M54 34 L53 15 L66 27 Z"/>',
        "50% 50%",
    ),
    ("cat", "ear"): (f'<path {_FL} d="M86 34 L87 15 L74 27 Z"/>', "57.1% 32%"),
    ("cat", "face"): (
        f'<circle {_FL} cx="70" cy="40" r="17"/>'
        f'<ellipse {_INK} cx="63" cy="39" rx="1.8" ry="2.8"/>'
        f'<ellipse {_INK} cx="77" cy="39" rx="1.8" ry="2.8"/>'
        f'<path {_INK} d="M68 45 H72 L70 47.5 Z"/>'
        f'<path {_THIN} d="M59 46 H48 M59 49 L49 52 M81 46 H92 M81 49 L91 52"/>',
        "50% 50%",
    ),
    ("other", "shadow"): (f'<ellipse {_SHADOW} cx="70" cy="94" rx="24" ry="3.5"/>', "50% 94%"),
    ("other", "base"): (
        f'<circle {_FL} cx="56" cy="44" r="7"/>'
        f'<circle {_FL} cx="84" cy="44" r="7"/>'
        f'<ellipse {_FL} cx="70" cy="66" rx="27" ry="24"/>'
        f'<path {_INK} d="M68 69 H72 L70 71.5 Z"/>'
        f'<path {_THIN} d="M66 74 Q70 77 74 74"/>'
        f'<ellipse {_FL} cx="59" cy="89" rx="7" ry="3"/>'
        f'<ellipse {_FL} cx="81" cy="89" rx="7" ry="3"/>',
        "50% 50%",
    ),
    ("other", "eye"): (
        f'<ellipse {_INK} cx="62" cy="62" rx="2.2" ry="2.8"/>'
        f'<ellipse {_INK} cx="78" cy="62" rx="2.2" ry="2.8"/>',
        "50% 62%",
    ),
}
_ART_CSS = "".join(
    f".pp-{species} .{part} {{ background-image: {_svg_url(body)}; transform-origin: {origin}; }}\n"
    for (species, part), (body, origin) in _PET_PARTS.items()
) + ".pp-other .hop { background: none; transform-origin: 50% 100%; }\n"

# Layer order is paint order. The critter's eyes sit inside the hop so they move with it.
_PET_LAYERS: dict[str, str] = {
    "dog": '<span class="tail"></span><span class="base"></span><span class="head"></span>',
    "cat": '<span class="tail"></span><span class="base"></span>'
    '<span class="ear"></span><span class="face"></span>',
    "other": '<span class="shadow"></span>'
    '<span class="hop"><span class="base"></span><span class="eye"></span></span>',
}


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

st.html(f"<style>{_CSS}{_ICON_CSS}{_ART_CSS}</style>")


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


def _editable_tasks(pet: Pet) -> list[Task]:
    """Return, per description + time, the earliest-due incomplete task.

    These are exactly the tasks Pet.update_task(), Pet.remove_task(), and
    Scheduler.mark_task_complete() act on, so the user can never pick one task
    and have a different one change.
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


def _product_label(product: FoodProduct) -> str:
    """Return a short label for a product in a dropdown (no "$": labels render Markdown)."""
    return f"{product.brand} · {product.name} ({product.price:.2f})"


def _escape_dollars(text: str) -> str:
    """Escape "$" so Streamlit's Markdown doesn't read prices as LaTeX math."""
    return text.replace("$", "\\$")


def _money(amount: float) -> str:
    """Format an amount as dollars for Markdown text."""
    return _escape_dollars(f"${amount:,.2f}")


def _plural(count: int, word: str) -> str:
    """Return "1 task" or "3 tasks"."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def _day_label(day: date) -> str:
    """Return "Today", "Tomorrow", or a short date like "Mon, Oct 19"."""
    if day == today:
        return "Today"
    if (day - today).days == 1:
        return "Tomorrow"
    return f"{day:%a, %b} {day.day}"


# --- HTML building blocks. Every value goes through _e() before it reaches HTML.

def _e(value: object) -> str:
    """Escape any value for safe use in HTML text or attributes."""
    return html.escape(str(value), quote=True)


def _icon(name: str) -> str:
    """Return a line icon (drawn by the .pp-i-<name> CSS mask)."""
    return f'<span class="pp-i pp-i-{name}" aria-hidden="true"></span>'


def _dot(kind: str, label: str) -> str:
    """Return a status dot (ok, warn, err, or neutral) with a screen-reader label."""
    return f'<span class="pp-dot {kind}" aria-hidden="true"></span><span class="pp-sr">{_e(label)}</span>'


def _row(
    icon: str,
    title: str,
    subtitle: str = "",
    meta: str = "",
    status: tuple[str, str] | None = None,
    chevron: bool = True,
) -> str:
    """Return one list row: icon, title, muted subtitle, then meta text and a dot or chevron."""
    sub = f'<div class="pp-sub">{_e(subtitle)}</div>' if subtitle else ""
    right = f"<span>{_e(meta)}</span>" if meta else ""
    if status is not None:
        right += _dot(*status)
    elif chevron:
        right += _icon("chevron")
    return (
        f'<div class="pp-row" role="listitem"><span class="pp-ico">{_icon(icon)}</span>'
        f'<div class="pp-txt"><div class="pp-title">{_e(title)}</div>{sub}</div>'
        f'<div class="pp-right">{right}</div></div>'
    )


def _list(rows: list[str], label: str) -> None:
    """Show read-only rows as one bordered list."""
    st.html(f'<div class="pp-list" role="list" aria-label="{_e(label)}">{"".join(rows)}</div>')


def _label(name: str, detail: str = "") -> None:
    """Show a small group label, e.g. a pet's name above its tasks."""
    extra = f" · {_e(detail)}" if detail else ""
    st.html(f'<div class="pp-label"><b>{_e(name)}</b>{extra}</div>')


def _empty(text: str) -> None:
    """Show a muted one-line empty state."""
    st.html(f'<p class="pp-empty">{_e(text)}</p>')


def _task_subtitle(task: Task, with_pet: bool = False) -> str:
    """Return a task's muted detail line."""
    parts = [_day_label(task.due_date), task.time]
    if with_pet:
        parts.append(task.pet_name)
    parts += [f"{task.duration_minutes} min", f"{task.priority.value} priority"]
    if task.frequency is not Frequency.ONCE:
        parts.append(task.frequency.value)
    return " · ".join(parts)


def _health_status() -> tuple[str, str]:
    """Return the header chip: any alert wins, then "no readings", else all healthy."""
    alerts = sum(len(p.health.check_alerts(p.species)) for p in owner.pets)
    if alerts:
        return "warn", _plural(alerts, "health alert")
    if not owner.pets or any(p.health.latest_reading() is None for p in owner.pets):
        return "", "No readings yet"
    return "ok", "All pets healthy"


def _pet_card(pet: Pet, entry: str | None) -> str:
    """Return one gallery card. `entry` marks a just-added pet so its card fades in once."""
    kind = pet.species if pet.species in _PET_LAYERS else "other"
    age = f"{pet.age_years:g} {'yr' if pet.age_years == 1 else 'yrs'}"
    classes = f"pp-card pp-{kind}" + (" is-new" if entry else "")
    data = f' data-entry="{_e(entry)}"' if entry else ""
    return (
        f'<article class="{classes}"{data} tabindex="0" '
        f'aria-label="{_e(pet.name)}, {_e(pet.species)}, {_e(age)}">'
        f'<div class="pp-art" aria-hidden="true">{_PET_LAYERS[kind]}</div>'
        f'<div class="pp-name">{_e(pet.name)}</div>'
        f'<div class="pp-meta">{_e(pet.species)} · {_e(age)}</div></article>'
    )


def _reading_row(reading: HealthReading, status: tuple[str, str] | None) -> str:
    """Return one collar reading as a list row."""
    r = reading
    return _row(
        "heart",
        f"{r.heart_rate_bpm} bpm · SpO2 {r.spo2_percent}% · {r.temperature_c} °C",
        f"{_day_label(r.timestamp.date())} {r.timestamp:%H:%M:%S} · breathing "
        f"{r.respiratory_rate}/min · sleep {r.sleep_score}/100 · {r.steps:,} steps · "
        f"{r.distance_km} km · {r.calories_burned} kcal",
        status=status,
    )


def _stats(summary: dict) -> str:
    """Return a daily_summary() dict as a quiet grid of value / label pairs."""
    cells = "".join(
        f'<div class="pp-stat"><div class="pp-stat-v">'
        f'{"–" if summary[key] is None else _e(f"{summary[key]}{unit}")}</div>'
        f'<div class="pp-stat-l">{_e(label)}</div></div>'
        for key, label, unit in SUMMARY_LABELS
    )
    return f'<div class="pp-stats">{cells}</div>'


def _mark_done(pet: Pet, task: Task) -> None:
    """Complete a task through the Scheduler and report its next occurrence, if any."""
    upcoming = Scheduler(owner).mark_task_complete(pet.name, task.description, task.time)
    # None means either "one-time task" or "no match"; the task's own flag tells them apart.
    if not task.completed:
        st.warning("That task could not be found. It may have been removed.")
        return
    message = f"Marked '{task.description}' done for {pet.name}."
    if upcoming is not None:
        message += f" Next: {_day_label(upcoming.due_date)} at {upcoming.time}."
    _flash(message, "Schedule")


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
                # A fresh counter per add, so the entrance plays even for a reused name.
                st.session_state["_pet_adds"] = st.session_state.get("_pet_adds", 0) + 1
                st.session_state["_new_pet"] = (clean_name, st.session_state["_pet_adds"])
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
# Header: title, today's numbers, health chip, pet gallery
# ---------------------------------------------------------------------------

scheduler = Scheduler(owner)
plan = scheduler.build_daily_plan(today)
skip_reasons = scheduler.skip_reasons(today)
used = sum(t.duration_minutes for t in plan)
available = owner.available_minutes
chip_kind, chip_text = _health_status()

st.html(
    '<header class="pp-head">'
    '<h1 class="pp-h1">PawPal+</h1>'
    f'<p class="pp-date">{today:%A, %B} {today.day} · {_plural(len(owner.pets), "pet")}</p>'
    '<div class="pp-summary"><div>'
    f'<div class="pp-big{" warn" if used > available else ""}">'
    f'<span class="pp-used">{used}</span> <span class="pp-of">/ {available} min</span></div>'
    f'<div class="pp-sum-sub">{_plural(len(plan), "task")} planned · {len(skip_reasons)} skipped</div>'
    "</div>"
    f'<span class="pp-chip"><span class="pp-dot {chip_kind}" aria-hidden="true"></span>'
    f"{_e(chip_text)}</span>"
    "</div></header>"
)
_show_flash()

if owner.pets:
    new_pet = st.session_state.pop("_new_pet", None)
    cards = [
        _pet_card(p, f"{p.name}-{new_pet[1]}" if new_pet and new_pet[0] == p.name else None)
        for p in owner.pets
    ]
    st.html(f'<section class="pp-gallery" aria-label="Your pets">{"".join(cards)}</section>')

# key + on_change="rerun" make the tabs remember the open tab, so the st.rerun()
# after every action lands the user back on the tab they were using.
schedule_tab, health_tab, shop_tab = st.tabs(TABS, key="main_tab", on_change="rerun")


# ===========================================================================
# Schedule tab
# ===========================================================================

with schedule_tab:
    _show_flash("Schedule")

    if not owner.pets:
        st.info("Add a pet in the sidebar to start adding tasks.")
    else:
        # --- Add a task -----------------------------------------------------
        with st.expander("Add a task", icon=":material/add:"):
            with st.form("add_task_form", clear_on_submit=True, border=False):
                task_pet_name = st.selectbox("Pet", [p.name for p in owner.pets])
                description = st.text_input("Description", placeholder="e.g. Morning walk")
                left, right = st.columns(2)
                task_type = left.selectbox("Task type", UI_TASK_TYPES)
                priority = right.selectbox(
                    "Priority", PRIORITIES, index=PRIORITIES.index("medium")
                )
                due_date = left.date_input("Due date", value=today)
                task_time = right.time_input("Time", value=dt_time(8, 0), step=300)
                duration = left.number_input(
                    "Duration (minutes)", min_value=1, max_value=240, value=15
                )
                frequency = right.selectbox("Frequency", FREQUENCIES)
                add_task_clicked = st.form_submit_button(
                    "Add task", type="primary", icon=":material/add_task:"
                )

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

        # --- Edit or remove a task ------------------------------------------
        pets_with_open_tasks = [p for p in owner.pets if _editable_tasks(p)]
        if pets_with_open_tasks:
            with st.expander("Edit or remove a task", icon=":material/edit:"):
                edit_pet_name = st.selectbox(
                    "Pet", [p.name for p in pets_with_open_tasks], key="edit_pet_name"
                )
                edit_pet = owner.get_pet(edit_pet_name) or pets_with_open_tasks[0]
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
                with st.form(f"{k}::form", border=False):
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
                                _flash(
                                    f"Updated '{clean_description}' for {edit_pet.name}.",
                                    "Schedule",
                                )
                            else:
                                st.warning("That task could not be found. It may have been removed.")

                if remove_clicked:
                    if edit_pet.remove_task(task.description, task.time):
                        _flash(f"Removed '{task.description}' from {edit_pet.name}.", "Schedule")
                    else:
                        st.warning("That task could not be found. It may already be removed.")

        # --- Task list, with "Mark done" on each task it would complete -----
        st.subheader("Tasks", anchor=False)
        for p_index, pet in enumerate(owner.pets):
            pet_tasks = sorted(pet.get_tasks(), key=lambda t: (t.due_date, t.time))
            _label(pet.name, _plural(len(pet_tasks), "task"))
            if not pet_tasks:
                _empty("No tasks yet.")
                continue
            actionable = set(_editable_tasks(pet))  # Task compares by identity
            with st.container(key=f"pp-alist-tasks-{p_index}"):
                for i, task in enumerate(pet_tasks):
                    with st.container(
                        horizontal=True,
                        vertical_alignment="center",
                        wrap=False,
                        gap=None,
                        key=f"pp-arow-tasks-{p_index}-{i}",
                    ):
                        if task.completed:
                            status: tuple[str, str] | None = ("ok", "done")
                        elif task in actionable:
                            status = None
                        else:
                            status = ("", "later occurrence")
                        st.html(
                            _row(
                                _TYPE_ICON[task.task_type],
                                task.description,
                                _task_subtitle(task) + (" · done" if task.completed else ""),
                                status=status,
                                chevron=False,
                            )
                        )
                        if task in actionable and st.button(
                            "Mark done",
                            key=f"done::{pet.name}::{task.description}::{task.time}::{task.due_date}",
                            type="tertiary",
                            icon=":material/check:",
                        ):
                            _mark_done(pet, task)

    # --- Today's plan -------------------------------------------------------
    st.subheader("Today's plan", anchor=False)
    if st.button("Build today's plan", type="primary", icon=":material/calendar_today:"):
        st.session_state["show_plan"] = True

    # Once built, the plan stays open and is recomputed on every run, so it
    # always reflects the latest tasks and sidebar constraints.
    if st.session_state.get("show_plan"):
        explanations = scheduler.explain_plan(today)
        conflicts = scheduler.detect_conflicts(today)

        if not plan and not skip_reasons:
            st.info("Nothing left to do today.")
        else:
            _label("Planned", _plural(len(plan), "task"))
            if plan:
                _list(
                    [
                        _row(
                            _TYPE_ICON[t.task_type],
                            t.description,
                            _task_subtitle(t, with_pet=True),
                            status=("ok", "planned"),
                        )
                        for t in plan
                    ],
                    "Today's plan",
                )
            else:
                _empty("No tasks fit today's plan.")

            if used <= available:
                st.success(
                    f"{_plural(len(plan), 'task')} planned: {used} of {available} min used "
                    f"({available - used} min free)."
                )
            else:
                st.warning(
                    f"{_plural(len(plan), 'task')} planned: {used} min, but only {available} "
                    "min available. Medication is always kept, so the plan goes over."
                )

            if skip_reasons:
                _label("Skipped", _plural(len(skip_reasons), "task"))
                _list(
                    [
                        _row(
                            _TYPE_ICON[t.task_type],
                            t.description,
                            f"{t.time} · {t.pet_name} · {t.duration_minutes} min · {reason}",
                            status=("warn", "skipped"),
                        )
                        for t, reason in skip_reasons.items()
                    ],
                    "Tasks skipped today and why",
                )

            _label("Why each task was planned or skipped")
            items = "".join(f"<li>{_e(line)}</li>" for line in explanations)
            st.html(f'<div class="pp-list"><ul class="pp-explain">{items}</ul></div>')

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
        st.subheader("Smart collar", anchor=False)
        if pet.collar is None:
            _list(
                [_row("collar", "No collar paired", f"Pair one to start {pet.name}'s readings.",
                      status=("", "not paired"))],
                "Smart collar",
            )
            with st.expander("Pair a collar", icon=":material/link:"):
                with st.form(f"pair_collar::{pet.name}", clear_on_submit=True, border=False):
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
                    pair_clicked = st.form_submit_button(
                        "Pair collar", type="primary", icon=":material/link:"
                    )

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
            with st.container(key="pp-alist-collar"):
                with st.container(
                    horizontal=True, vertical_alignment="center", wrap=False, gap=None,
                    key="pp-arow-collar",
                ):
                    st.html(
                        _row(
                            "collar",
                            f"Collar {pet.collar.device_id}",
                            f"Battery {pet.collar.battery_percent}% · set up for {pet.species}",
                            status=("ok", "paired"),
                        )
                    )
                    if st.button(
                        "Sync now", icon=":material/sync:", type="tertiary", key=f"sync::{pet.name}"
                    ):
                        reading = pet.sync_collar(datetime.now())
                        if reading is None:
                            st.warning(f"{pet.name} has no collar paired.")
                        else:
                            _flash(
                                f"New reading for {pet.name} at {reading.timestamp:%H:%M:%S}.",
                                "Health",
                            )

        # --- Alerts ---------------------------------------------------------
        st.subheader("Alerts", anchor=False)
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

        # --- Readings and today's summary -----------------------------------
        st.subheader("Readings", anchor=False)
        readings = sorted(pet.health.readings, key=lambda r: r.timestamp, reverse=True)
        if readings:
            # check_alerts() judges the latest reading only, so only that row gets a dot.
            if alerts:
                latest_status = ("warn", "outside the normal range")
            elif pet.species in VITAL_RANGES:
                latest_status = ("ok", "within the normal range")
            else:
                latest_status = ("", "no normal range for this species")
            _list(
                [
                    _reading_row(r, latest_status if i == 0 else None)
                    for i, r in enumerate(readings[:MAX_READINGS_SHOWN])
                ],
                f"{pet.name}'s latest collar readings",
            )
            if len(readings) > MAX_READINGS_SHOWN:
                st.caption(f"Showing the latest {MAX_READINGS_SHOWN} of {len(readings)} readings.")
        else:
            _empty("No readings yet. Pair a collar and press Sync now.")

        _label("Today's summary", f"{today:%B} {today.day}")
        st.html(_stats(pet.health.daily_summary(today)))

        # --- Medications ----------------------------------------------------
        st.subheader("Medications", anchor=False)
        if pet.health.medications:
            _list(
                [
                    _row(
                        "medication",
                        f"{m.name} · {m.dose}",
                        f"{', '.join(m.times)} · {m.frequency.value} · from "
                        f"{m.start_date:%b} {m.start_date.day}, {m.start_date.year}",
                    )
                    for m in pet.health.medications
                ],
                f"{pet.name}'s medications",
            )
        else:
            _empty("No medications yet.")
        with st.expander("Add a medication", icon=":material/medication:"):
            with st.form(f"add_med::{pet.name}", clear_on_submit=True, border=False):
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
                add_med_clicked = st.form_submit_button(
                    "Add medication", type="primary", icon=":material/medication:"
                )

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
        st.subheader("Symptoms", anchor=False)
        if pet.health.symptoms:
            _list(
                [
                    _row(
                        "note",
                        s.description,
                        f"{_day_label(s.logged_on)} · {s.severity.value}",
                        status=("", "mild") if s.severity is Severity.MILD
                        else ("warn", s.severity.value),
                    )
                    for s in sorted(pet.health.symptoms, key=lambda s: s.logged_on, reverse=True)
                ],
                f"{pet.name}'s symptom log",
            )
        else:
            _empty("No symptoms logged.")
        with st.expander("Log a symptom", icon=":material/edit_note:"):
            with st.form(f"log_symptom::{pet.name}", clear_on_submit=True, border=False):
                symptom = st.text_input("Symptom", placeholder="e.g. Limping on front left leg")
                severity = st.selectbox("Severity", SEVERITIES)
                log_clicked = st.form_submit_button(
                    "Log symptom", type="primary", icon=":material/edit_note:"
                )

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
        st.subheader("Conditions and allergies", anchor=False)
        _list(
            [
                _row("shield", "Conditions", ", ".join(pet.health.conditions) or "None"),
                _row("shield", "Allergies", ", ".join(pet.health.allergies) or "None"),
            ],
            f"{pet.name}'s conditions and allergies",
        )
        with st.expander("Edit conditions and allergies", icon=":material/edit:"):
            with st.form(f"health_lists::{pet.name}", border=False):
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
                lists_clicked = st.form_submit_button(
                    "Save conditions and allergies", type="primary"
                )

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
        st.subheader(f"Recommended for {pet.name}", anchor=False)
        if safe:
            _list(
                [
                    _row(
                        "food",
                        f"{rank}. {product.brand} · {product.name}",
                        " · ".join(market.explain_recommendation(product, pet)),
                        f"${product.price:.2f} · score {market.score(product, pet):g}",
                        status=("ok", "safe"),
                    )
                    for rank, product in enumerate(safe[:3], start=1)
                ],
                f"Top food picks for {pet.name}",
            )
        else:
            st.info(f"This store has no food that is safe for {pet.name}.")

        if excluded:
            with st.expander(
                f"Not recommended for {pet.name} ({len(excluded)})", icon=":material/block:"
            ):
                _list(
                    [
                        _row(
                            "food",
                            f"{p.brand} · {p.name}",
                            market.explain_recommendation(p, pet)[0],
                            status=("warn", "not recommended"),
                        )
                        for p in excluded
                    ],
                    f"Products excluded for {pet.name} and why",
                )

        # --- Search ---------------------------------------------------------
        with st.expander("Search", icon=":material/search:"):
            query = st.text_input(
                "Search by name or brand", placeholder="e.g. salmon", key="shop_query"
            ).strip()
            if query:
                results = market.search(pet.species, query)
                if results:
                    _list(
                        [
                            _row(
                                "food",
                                f"{p.brand} · {p.name}",
                                f"Rating {p.rating} · "
                                + (f"safe for {pet.name}" if p.product_id in safe_ids
                                   else f"not safe for {pet.name}"),
                                f"${p.price:.2f}",
                                status=("ok", "safe") if p.product_id in safe_ids
                                else ("warn", "not safe"),
                            )
                            for p in results
                        ],
                        "Search results",
                    )
                else:
                    st.caption(f"No {pet.species} food matches '{query}'.")

        # --- Compare --------------------------------------------------------
        with st.expander("Compare", icon=":material/compare_arrows:"):
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
        with st.expander("Add to cart", icon=":material/add_shopping_cart:"):
            if safe:
                with st.form(f"add_to_cart::{pet.name}", clear_on_submit=True, border=False):
                    product_id = st.selectbox(
                        "Product",
                        [p.product_id for p in safe],
                        format_func=lambda pid: _product_label(products_by_id[pid]),
                        help=f"Only food that is safe for {pet.name} is listed.",
                    )
                    quantity = st.number_input(
                        "Quantity", min_value=1, max_value=20, value=1, step=1
                    )
                    add_clicked = st.form_submit_button(
                        "Add to cart", type="primary", icon=":material/add_shopping_cart:"
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
        st.subheader("Cart", anchor=False)
        if owner.cart.items:
            with st.container(key="pp-alist-cart"):
                for i, item in enumerate(owner.cart.items):
                    product = item.product
                    with st.container(
                        horizontal=True, vertical_alignment="center", wrap=False, gap=None,
                        key=f"pp-arow-cart-{i}",
                    ):
                        st.html(
                            _row(
                                "food",
                                f"{product.brand} · {product.name}",
                                f"{item.quantity} × ${product.price:.2f}",
                                f"${item.subtotal():.2f}",
                                chevron=False,
                            )
                        )
                        if st.button(
                            "Remove",
                            key=f"remove::{product.product_id}",
                            type="tertiary",
                            icon=":material/close:",
                        ):
                            if owner.cart.remove_item(product.product_id):
                                _flash(f"Removed {product.name} from your cart.", "Shop")
                            else:
                                st.warning("That item is no longer in your cart.")
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
                        f"Delivery on {order.delivery_date:%A, %B} {order.delivery_date.day}; "
                        f"a reminder was added to {pet.name}'s schedule.",
                        "Shop",
                    )
        else:
            _empty("Your cart is empty.")

        # --- Orders ---------------------------------------------------------
        st.subheader("Orders", anchor=False)
        if owner.orders:
            with st.container(key="pp-alist-orders"):
                for order in reversed(owner.orders):
                    delivered = order.status is OrderStatus.DELIVERED
                    with st.container(
                        horizontal=True, vertical_alignment="center", wrap=False, gap=None,
                        key=f"pp-arow-order-{order.order_id}",
                    ):
                        st.html(
                            _row(
                                "delivery",
                                f"{order.order_id} · {_plural(sum(i.quantity for i in order.items), 'item')}",
                                f"Placed {_day_label(order.placed_on)} · delivery "
                                f"{_day_label(order.delivery_date)} · {order.status.value}",
                                f"${order.total:.2f}",
                                status=("ok", "delivered") if delivered else ("", order.status.value),
                            )
                        )
                        if not delivered and st.button(
                            "Advance status",
                            key=f"advance::{order.order_id}",
                            type="tertiary",
                            icon=":material/arrow_forward:",
                        ):
                            order.advance_status()
                            _flash(f"Order {order.order_id} is now {order.status.value}.", "Shop")
        else:
            _empty("No orders yet.")
